# -*- coding: utf-8 -*-
"""Onde mora a concessão: no grupo, não no agente e não no código.

O `liber_roles` estabeleceu que uma decisão de acesso pertence ao repositório,
onde pode ser lida e revisada. Aqui a decisão é outra -- "esta função pode
pedir ao agente que faça o quê, e até quantos documentos por vez" -- mas o
lugar é o mesmo: um campo em `res.groups`, preenchido por arquivo de dados.

Por que no grupo e não no agente: porque a pergunta que um diretor faz é "o que
o comercial pode automatizar?", não "o que o agente Fulano pode fazer?". A
resposta precisa estar do lado da função. O agente também tem a sua lista, e o
que vale é a interseção -- ver capela_ai_agent.py.

Concessões acumulam pela união, e o teto pelo máximo. Um diretor que também
opera o comercial soma as duas listas e fica com o maior teto: a autoridade de
uma pessoa é a união das funções dela, não a interseção. É a mesma aritmética
dos `implied_ids` do Odoo, e ela precisa ser a mesma para não surpreender.
"""

from odoo import fields, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    capela_ai_tool_ids = fields.Many2many(
        'capela.ai.tool',
        'capela_ai_tool_group_rel', 'group_id', 'tool_id',
        string='Ferramentas do agente',
        help="O que uma pessoa desta função pode pedir ao agente. Vale a "
             "interseção com a lista do próprio agente, e o ORM ainda barra o "
             "que a pessoa não poderia fazer com as próprias mãos.",
    )
    capela_ai_max_records = fields.Integer(
        string='Documentos por plano',
        help="Teto de documentos que um único plano pode tocar. Zero significa "
             "que esta função não age pelo agente. Quem acumula funções fica "
             "com o maior teto.",
    )


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _capela_ai_tools(self):
        """A união das ferramentas concedidas às funções desta pessoa."""
        self.ensure_one()
        return self.env['capela.ai.tool'].browse(
            self.sudo().groups_id.capela_ai_tool_ids.ids
        )

    def _capela_ai_max_records(self):
        """O maior teto entre as funções desta pessoa; zero se nenhuma concede."""
        self.ensure_one()
        caps = self.sudo().groups_id.mapped('capela_ai_max_records')
        return max(caps or [0])
