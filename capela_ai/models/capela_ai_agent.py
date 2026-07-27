# -*- coding: utf-8 -*-
"""O agente, e a interseção tripla que define o que ele consegue fazer por você.

Um agente é uma configuração: um modelo do Claude, uma instrução de sistema,
uma lista de ferramentas e uma lista de funções que podem invocá-lo. O que ele
efetivamente pode fazer numa conversa não está em nenhuma dessas listas
isoladamente -- está na interseção de três coisas:

    ferramentas do agente
      ∩ ferramentas concedidas às funções de quem pediu   (res.groups)
      ∩ o que o ORM deixaria essa pessoa fazer com as mãos

As duas primeiras são calculadas aqui, no servidor, e o resultado é o que vai
para o parâmetro `tools` da API -- o modelo nunca vê a existência do que não
pode chamar. A terceira não é calculada por ninguém: ela acontece sozinha, na
hora de gravar, porque tudo roda como `env.user`. É a que dá a garantia mais
forte, justamente por não depender de nós lembrarmos dela.

Ordem de renderização da API é `tools` -> `system` -> `messages`, e o cache de
prefixo é casamento exato de bytes. Como a lista de ferramentas é derivada de
grupos -- determinística para um par (agente, pessoa) -- o prefixo é estável e
a conversa inteira lê cache. Isso só continua verdade se nada volátil entrar no
`system`: nem data, nem nome de usuário, nem id de sessão. Esses vão em
`messages`, depois do ponto de corte.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from ..tools import registry
from .ir_model_access import CTX_PLANNING


class CapelaAiAgent(models.Model):
    _name = 'capela.ai.agent'
    _description = 'Agente'
    _order = 'sequence, name'

    name = fields.Char(string='Nome', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Char(
        string='Modelo', required=True, default='claude-opus-5',
        help="Identificador do modelo na API. Trocar isto invalida o cache de "
             "prefixo das conversas em andamento -- caches são por modelo.",
    )
    system_prompt = fields.Text(
        string='Instrução de sistema',
        help="Estável de propósito: nada de data, nome de usuário ou id de "
             "sessão aqui, senão o cache de prefixo nunca acerta.",
    )
    tool_ids = fields.Many2many(
        'capela.ai.tool', 'capela_ai_agent_tool_rel', 'agent_id', 'tool_id',
        string='Ferramentas',
    )
    group_ids = fields.Many2many(
        'res.groups', 'capela_ai_agent_group_rel', 'agent_id', 'group_id',
        string='Funções que podem usar',
        help="Vazio significa ninguém. É deliberado: um agente novo nasce "
             "inacessível, e liberar é um ato explícito.",
    )

    # ------------------------------------------------------------------
    # Capacidade
    # ------------------------------------------------------------------

    def _check_invocable(self):
        """Esta pessoa pode falar com este agente?"""
        self.ensure_one()
        user = self.env.user
        if not self.active:
            raise UserError(_("O agente %(name)s está desativado.", name=self.name))
        if not (self.group_ids & user.sudo().groups_id):
            raise AccessError(_(
                "Seu perfil não tem acesso ao agente %(name)s.", name=self.name,
            ))

    def _effective_tools(self):
        """As duas primeiras interseções. A terceira o ORM faz sozinho."""
        self.ensure_one()
        self._check_invocable()
        granted = self.env.user._capela_ai_tools()
        allowed = self.tool_ids & granted
        return [
            registry.get(record.name)
            for record in allowed
            if record.name in registry.REGISTRY
        ]

    def api_tool_schemas(self):
        """O que vai no parâmetro `tools` da chamada. Ordenado: cache exige bytes iguais."""
        self.ensure_one()
        return [
            tool_def.to_api_schema()
            for tool_def in sorted(self._effective_tools(), key=lambda t: t.name)
        ]

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------

    def execute_tool(self, name, params):
        """Ponto único de entrada para tudo que o modelo pede.

        Devolve `(kind, payload)`: para uma consulta, os dados; para um plano,
        o registro `capela.ai.plan` que espera aprovação. Quem chamou decide
        como mostrar -- este método não conhece interface.
        """
        self.ensure_one()
        self._check_invocable()

        available = {tool_def.name for tool_def in self._effective_tools()}
        if name not in available:
            # Mensagem honesta e sem detalhe: se a ferramenta existe mas não foi
            # concedida, dizer isso ao modelo só o convida a insistir.
            raise AccessError(_(
                "A ferramenta %(name)s não está disponível nesta conversa.", name=name,
            ))

        tool_def = registry.get(name)
        params = params or {}

        if tool_def.kind == registry.KIND_READ:
            # Sem contexto especial: a consulta roda como a pessoa, e as ACLs e
            # record rules dela são exatamente o limite que queremos.
            return tool_def.kind, tool_def.handler(self.env, **params)

        # Planejar não grava. O contexto transforma isso de promessa em
        # propriedade verificável -- ver models/ir_model_access.py.
        planning_env = self.env(context=dict(self.env.context, **{CTX_PLANNING: True}))
        spec = tool_def.handler(planning_env, **params)
        plan = self.env['capela.ai.plan']._build(self, tool_def, spec)
        return tool_def.kind, plan
