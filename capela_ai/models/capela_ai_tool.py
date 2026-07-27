# -*- coding: utf-8 -*-
"""O espelho em banco do catálogo que mora em Python.

O registro de ferramentas é código (tools/registry.py) e continua sendo: quem
decide o que o agente sabe fazer é um commit, não um clique. Mas a CONCESSÃO --
qual função pode chamar qual ferramenta -- é dado, e dado precisa de registro
para virar many2many, aparecer em tela e ser referenciado por XML.

Daí este modelo: um espelho, sincronizado a cada instalação ou atualização do
módulo. Ninguém cria ferramenta aqui. Se a linha existe e o Python não a
declara mais, ela é ARQUIVADA em vez de apagada -- porque concessões apontam
para ela, e apagar transformaria uma revogação deliberada em cascata silenciosa.
"""

from odoo import api, fields, models

from ..tools import registry


class CapelaAiTool(models.Model):
    _name = 'capela.ai.tool'
    _description = 'Ferramenta do agente'
    _order = 'kind, name'

    name = fields.Char(
        string='Nome técnico', required=True, index=True, readonly=True,
        help="O nome pelo qual o modelo chama a ferramenta. Vem do Python.",
    )
    title = fields.Char(string='Título', readonly=True)
    description = fields.Text(string='Descrição', readonly=True)
    kind = fields.Selection(
        [
            (registry.KIND_READ, 'Consulta'),
            (registry.KIND_PLAN, 'Propõe (exige aprovação)'),
        ],
        string='Tipo', readonly=True, required=True,
    )
    writes = fields.Char(
        string='Modelos que altera', readonly=True,
        help="Declarado no código. O guarda recusa qualquer modelo fora desta lista.",
    )
    automation_safe = fields.Boolean(
        string='Pode rodar sem humano', readonly=True,
        help="Reservado para a automação (v2). Na v1 todo plano passa por "
             "aprovação, então este campo ainda não muda nada.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Cada ferramenta aparece uma vez só.'),
    ]

    @api.model
    def _xmlid_for(self, name):
        """`query.search` -> `capela_ai.tool_query_search`.

        Sem XML id, nenhum outro módulo consegue referenciar uma ferramenta em
        arquivo de dados -- e é exatamente isso que o `capela_ai_roles` precisa
        fazer para conceder ferramentas às funções da casa. Como os registros
        nascem de código e não de XML, o id tem de ser criado aqui.
        """
        return 'capela_ai.tool_%s' % name.replace('.', '_')

    @api.model
    def _sync_from_registry(self):
        """Reconcilia o espelho com o Python. Idempotente."""
        declared = registry.REGISTRY
        existing = {rec.name: rec for rec in self.with_context(active_test=False).search([])}

        for name, tool_def in declared.items():
            vals = {
                'title': tool_def.title,
                'description': tool_def.description,
                'kind': tool_def.kind,
                'writes': ', '.join(sorted(tool_def.writes)) or False,
                'automation_safe': tool_def.automation_safe,
                'active': True,
            }
            record = existing.get(name)
            if record:
                record.write(vals)
            else:
                record = self.create(dict(vals, name=name))
            self.env['ir.model.data']._update_xmlids([{
                'xml_id': self._xmlid_for(name),
                'record': record,
                'noupdate': True,
            }])

        # Sumiu do código: arquiva, não apaga. Ver o docstring do módulo.
        orphans = [rec for name, rec in existing.items() if name not in declared and rec.active]
        for record in orphans:
            record.active = False

    def init(self):
        """Chamado pelo Odoo a cada instalação ou atualização do módulo."""
        super().init()
        self._sync_from_registry()
