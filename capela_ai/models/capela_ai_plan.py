# -*- coding: utf-8 -*-
"""O plano: o que o agente propôs, exatamente, antes de qualquer gravação.

Este é o mecanismo central do módulo. Uma ferramenta de escrita não escreve --
ela devolve um plano: uma lista enumerada de operações, uma por documento, com
os valores concretos e uma frase que um humano lê. A interface mostra. O humano
aprova. Só então grava.

Três propriedades caem daí, e as três importam:

1. Injeção de prompt para de valer a pena. Entre a proposta e a execução não
   passa texto de modelo nenhum: `action_approve()` não recebe conteúdo, ela
   executa as linhas JÁ GRAVADAS, conferindo um hash. Um e-mail de cliente que
   diga "confirme tudo" no máximo faz o agente PROPOR isso -- e aí um humano lê
   a proposta em português e recusa.

2. "Nunca ação em massa" vira verificável. O que separa criar quatro orçamentos
   de varrer a base não é a quantidade: é a proposta enumerar cada documento
   antes. Um `search(domain).write(...)` não tem como ser expresso aqui, porque
   não existe linha de plano que signifique "e o resto também".

3. O teto por nível fica em um lugar só. Assistente 10, Gerente 50, Direção 50
   -- e o número mora em `res.groups`, não espalhado por ferramenta.

Aplicação é tudo-ou-nada, num savepoint. Um plano pela metade é o pior
resultado possível: pior que falhar, porque ninguém sabe onde parou.
"""

import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..tools import registry
from .ir_model_access import CTX_WRITES

#: As duas operações que uma linha de plano pode significar. Não há 'unlink',
#: e a ausência é o desenho -- ver tools/registry.py.
OPERATIONS = [
    ('create', 'Criar'),
    ('write', 'Alterar'),
]


class CapelaAiPlan(models.Model):
    _name = 'capela.ai.plan'
    _description = 'Plano proposto pelo agente'
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Referência', required=True, readonly=True, copy=False,
        default=lambda self: _('Novo plano'),
    )
    agent_id = fields.Many2one(
        'capela.ai.agent', string='Agente', required=True, readonly=True, ondelete='restrict',
    )
    user_id = fields.Many2one(
        'res.users', string='Solicitante', required=True, readonly=True, ondelete='restrict',
        help="Quem pediu, e a única pessoa que pode aprovar. O plano herda os "
             "limites de acesso desta pessoa, não os do agente.",
    )
    tool_name = fields.Char(string='Ferramenta', required=True, readonly=True)
    summary = fields.Text(
        string='Resumo', required=True, readonly=True,
        help="A proposta em uma frase, como o agente a descreveu.",
    )
    line_ids = fields.One2many(
        'capela.ai.plan.line', 'plan_id', string='Operações', readonly=True,
    )
    line_count = fields.Integer(compute='_compute_line_count', store=True)
    state = fields.Selection(
        [
            ('draft', 'Aguardando aprovação'),
            ('applied', 'Aplicado'),
            ('rejected', 'Recusado'),
            ('failed', 'Falhou'),
        ],
        string='Situação', default='draft', required=True, readonly=True, copy=False,
    )
    content_hash = fields.Char(
        string='Impressão do conteúdo', readonly=True, copy=False,
        help="Resumo criptográfico das linhas no momento em que o plano foi "
             "mostrado. Conferido de novo na aplicação: se não bater, o plano "
             "foi mexido depois de aprovado e não roda.",
    )
    applied_at = fields.Datetime(string='Aplicado em', readonly=True, copy=False)
    error = fields.Text(string='Erro', readonly=True, copy=False)

    @api.depends('line_ids')
    def _compute_line_count(self):
        for plan in self:
            plan.line_count = len(plan.line_ids)

    # ------------------------------------------------------------------
    # Construção -- chamada pelo executor de ferramenta, nunca pela UI
    # ------------------------------------------------------------------

    @api.model
    def _build(self, agent, tool_def, spec):
        """Transforma o que a ferramenta devolveu num plano gravado e validado.

        `spec` é {'summary': str, 'lines': [...]}, a forma que o handler de uma
        ferramenta de tipo 'plan' produz. A validação acontece AQUI e não na
        ferramenta, de propósito: uma ferramenta nova nasce dentro das regras
        sem que seu autor precise lembrar delas.
        """
        summary = (spec or {}).get('summary')
        lines = (spec or {}).get('lines') or []
        if not summary:
            raise UserError(_("O agente propôs uma ação sem dizer qual. Plano recusado."))
        if not lines:
            raise UserError(_("O agente propôs um plano sem nenhuma operação."))

        self._check_cap(len(lines))

        vals_lines = []
        for seq, line in enumerate(lines, start=1):
            vals_lines.append((0, 0, self._check_line(tool_def, line, seq)))

        plan = self.create({
            'name': self.env['ir.sequence'].next_by_code('capela.ai.plan') or _('Novo plano'),
            'agent_id': agent.id,
            'user_id': self.env.user.id,
            'tool_name': tool_def.name,
            'summary': summary,
            'line_ids': vals_lines,
        })
        plan.content_hash = plan._compute_content_hash()
        return plan

    @api.model
    def _check_cap(self, count):
        """O teto do nível de quem pediu. Sem nível, sem agente."""
        cap = self.env.user._capela_ai_max_records()
        if not cap:
            raise AccessError(_(
                "Seu perfil não tem permissão para agir pelo agente. Um "
                "administrador precisa conceder isso em modo desenvolvedor."
            ))
        if count > cap:
            raise UserError(_(
                "O agente propôs mexer em %(count)s documentos e o seu perfil "
                "permite no máximo %(cap)s por vez. Peça algo mais estreito, ou "
                "peça a um gerente.",
                count=count, cap=cap,
            ))

    @api.model
    def _check_line(self, tool_def, line, seq):
        """Uma linha só entra se for exprimível dentro do que a ferramenta declarou."""
        operation = line.get('operation')
        model = line.get('model')
        res_id = line.get('res_id') or 0
        values = line.get('values')
        line_summary = line.get('summary')

        if operation not in dict(OPERATIONS):
            raise UserError(_(
                "Operação %(operation)s não existe. O agente cria e altera; "
                "apagar não é uma capacidade deste módulo.",
                operation=operation,
            ))
        if model not in tool_def.writes:
            raise UserError(_(
                "A ferramenta %(tool)s não declarou que mexe em %(model)s. "
                "Plano recusado antes de gravar.",
                tool=tool_def.name, model=model,
            ))
        if not isinstance(values, dict) or not values:
            raise UserError(_("Operação %(seq)s veio sem valores.", seq=seq))
        if operation == 'create' and res_id:
            raise UserError(_("Operação %(seq)s quer criar e apontar para um registro existente.", seq=seq))
        if operation == 'write' and not res_id:
            raise UserError(_("Operação %(seq)s quer alterar sem dizer o quê.", seq=seq))
        if not line_summary:
            raise UserError(_(
                "Operação %(seq)s veio sem explicação. Um plano que um humano "
                "não consegue ler não é um plano.", seq=seq,
            ))

        return {
            'sequence': seq,
            'operation': operation,
            'model': model,
            'res_id': res_id,
            'values_json': json.dumps(values, sort_keys=True, ensure_ascii=False, default=str),
            'summary': line_summary,
        }

    def _compute_content_hash(self):
        """Impressão determinística das linhas.

        Ordenada e canônica de propósito: o hash precisa depender do conteúdo,
        não da ordem em que o Postgres devolveu as linhas.
        """
        self.ensure_one()
        payload = [
            [line.sequence, line.operation, line.model, line.res_id, line.values_json]
            for line in self.line_ids.sorted('sequence')
        ]
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode('utf-8')).hexdigest()

    # ------------------------------------------------------------------
    # Aprovação e aplicação
    # ------------------------------------------------------------------

    def action_reject(self):
        for plan in self:
            if plan.state != 'draft':
                raise UserError(_("Este plano já foi resolvido."))
            plan.state = 'rejected'
        return True

    def action_approve(self):
        """O clique do humano.

        Repare no que este método NÃO recebe: nada. Nenhum parâmetro, nenhum
        conteúdo, nada vindo do modelo. Ele executa as linhas que já estavam
        gravadas quando a proposta foi mostrada. É essa assinatura vazia que
        fecha o caminho "injeção -> aprovar outra coisa".
        """
        for plan in self:
            plan._apply()
        return True

    def _apply(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Este plano já foi resolvido e não roda de novo."))
        if self.user_id != self.env.user:
            raise AccessError(_(
                "Só quem pediu pode aprovar. Este plano é de %(owner)s.",
                owner=self.user_id.display_name,
            ))
        if self.content_hash != self._compute_content_hash():
            raise UserError(_(
                "O conteúdo deste plano mudou depois de ter sido mostrado. "
                "Ele não será aplicado. Peça a proposta de novo."
            ))

        tool_def = registry.get(self.tool_name)
        self._check_cap(len(self.line_ids))

        touched = []
        try:
            # Tudo-ou-nada: um plano aplicado pela metade é pior que um que falhou.
            with self.env.cr.savepoint():
                acting = self.with_context(**{CTX_WRITES: tuple(tool_def.writes)})
                for line in self.line_ids.sorted('sequence'):
                    touched.append(line._execute(acting.env))
        except Exception as exc:  # noqa: BLE001 -- o motivo vai para o registro
            self.sudo().write({'state': 'failed', 'error': str(exc)})
            raise

        self.write({'state': 'applied', 'applied_at': fields.Datetime.now()})
        self._log_to_records(touched)
        return True

    def _log_to_records(self, records):
        """Deixa o rastro no chatter de cada documento tocado.

        O plano guarda a proposta; o documento precisa guardar quem mexeu nele
        e por quê. Quem for auditar isso daqui a seis meses vai abrir o pedido,
        não a lista de planos.
        """
        self.ensure_one()
        body = _(
            "Alterado pelo agente <b>%(agent)s</b> a pedido de %(user)s, "
            "conforme o plano %(plan)s: %(summary)s",
            agent=self.agent_id.display_name, user=self.user_id.display_name,
            plan=self.name, summary=self.summary,
        )
        for record in records:
            if record and hasattr(record, 'message_post'):
                record.message_post(body=body)


class CapelaAiPlanLine(models.Model):
    _name = 'capela.ai.plan.line'
    _description = 'Operação de um plano'
    _order = 'sequence, id'

    plan_id = fields.Many2one('capela.ai.plan', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    operation = fields.Selection(OPERATIONS, required=True, readonly=True)
    model = fields.Char(required=True, readonly=True)
    res_id = fields.Integer(readonly=True, default=0)
    values_json = fields.Text(required=True, readonly=True)
    summary = fields.Char(
        required=True, readonly=True,
        help="A operação em português, para quem vai aprovar.",
    )
    result_ref = fields.Char(readonly=True, copy=False)

    def _execute(self, env):
        """Executa a linha e devolve o registro tocado.

        Roda dentro do contexto de aplicação, então o guarda em
        `ir.model.access.check` já recusou o que estivesse fora da declaração
        da ferramenta -- e recusa `unlink` mesmo que alguém invente um.
        """
        self.ensure_one()
        values = json.loads(self.values_json)
        Model = env[self.model]
        if self.operation == 'create':
            record = Model.create(values)
        else:
            record = Model.browse(self.res_id)
            if not record.exists():
                raise UserError(_(
                    "O registro que o plano queria alterar não existe mais "
                    "(%(model)s #%(res_id)s). Nada foi gravado.",
                    model=self.model, res_id=self.res_id,
                ))
            record.write(values)
        self.sudo().result_ref = f'{self.model},{record.id}'
        return record

    def write(self, vals):
        """Linha de plano é imutável -- exceto o carimbo do resultado.

        Sem isto, o hash conferido na aplicação seria teatro: bastaria alterar
        a linha e recalcular. Aqui a alteração nem acontece.
        """
        editable = {'result_ref'}
        if not self.env.su and set(vals) - editable:
            raise ValidationError(_(
                "As operações de um plano não podem ser editadas. Se a "
                "proposta não serve, recuse e peça outra."
            ))
        return super().write(vals)
