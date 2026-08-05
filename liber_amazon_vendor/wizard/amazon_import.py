# -*- coding: utf-8 -*-
"""
Ler antes de gravar.

O assistente existe porque o problema da importação nunca foi a Amazon -- é o
nosso cadastro. Descobrir no meio de um cron que quinze títulos não têm
produto é o pior momento possível. Aqui a pessoa vê a conta antes: quantos
pedidos, quantos exemplares, quanto dinheiro, e a lista exata dos ISBNs que
não casam. Só então decide gravar.
"""

import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..services import mapping


class LiberAmazonImport(models.TransientModel):
    _name = 'liber.amazon.import'
    _description = 'Import Amazon Vendor Orders'

    account_id = fields.Many2one(
        'liber.amazon.account', required=True,
        default=lambda self: self.env['liber.amazon.account'].search([], limit=1))
    date_from = fields.Datetime(
        required=True,
        default=lambda self: fields.Datetime.subtract(
            fields.Datetime.now(), days=30))
    date_to = fields.Datetime(default=lambda self: fields.Datetime.now())

    state = fields.Selection(
        [('draft', 'Choose the window'), ('preview', 'Read from Amazon')],
        default='draft')

    payload_json = fields.Text(readonly=True)

    order_count = fields.Integer(readonly=True)
    open_count = fields.Integer(readonly=True)
    line_count = fields.Integer(readonly=True)
    quantity_total = fields.Float(readonly=True)
    amount_total = fields.Float(readonly=True)
    isbn_count = fields.Integer(readonly=True)
    matched_count = fields.Integer(readonly=True)
    unmatched_isbns = fields.Text(readonly=True)
    warnings = fields.Text(readonly=True)

    @api.model
    def default_get(self, fields_list):
        """
        Falha na abertura, e dizendo por quê.

        Sem isto, quem não enxerga nenhuma conta recebe um campo obrigatório
        vazio com um "Criar..." solitário — e a causa quase nunca é conta
        inexistente, é **empresa errada no seletor**: a conta pertence a uma
        empresa e a regra multiempresa a esconde das outras. Um combo vazio
        não conta essa história; esta mensagem conta.
        """
        values = super().default_get(fields_list)
        Account = self.env['liber.amazon.account']
        if not Account.search_count([]):
            existe_em_outra = Account.sudo().search_count([]) > 0
            if existe_em_outra:
                raise UserError(_(
                    "No Amazon account for %(company)s.\n\nOne exists for "
                    "another company. Switch company in the top-right "
                    "selector, or create an account for this one under "
                    "Configuration > Settings.",
                    company=self.env.company.display_name))
            raise UserError(_(
                "No Amazon account yet.\n\nCreate one under "
                "Configuration > Settings, with the credentials from the "
                "app in Amazon Developer Central."))
        return values

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_to and wizard.date_to <= wizard.date_from:
                raise UserError(_("The end of the window comes before its start."))

    def action_preview(self):
        """
        Vai à Amazon, conta o que veio, e não grava nada.

        O payload cru fica guardado no assistente para que a gravação use
        exatamente o que foi mostrado. Buscar de novo na hora de importar
        abriria uma janela -- pequena, mas real -- em que a pessoa aprova um
        relatório e o sistema grava outro.
        """
        self.ensure_one()
        orders = self.account_id._api().purchase_orders(
            self.date_from, self.date_to)

        report = mapping.import_report(orders)
        products = self.env['liber.amazon.order']._match_products(report['isbns'])
        unmatched = [isbn for isbn in report['isbns'] if isbn not in products]

        warnings = []
        if report['unknown_states']:
            warnings.append(_(
                "Amazon used states this module does not know yet: %s. They "
                "were imported anyway and are flagged.",
                ", ".join(report['unknown_states'])))
        if report['lines_without_isbn']:
            warnings.append(_(
                "%s line(s) carry no ISBN at all and can never be matched.",
                report['lines_without_isbn']))

        self.write({
            'state': 'preview',
            'payload_json': json.dumps(orders),
            'order_count': report['orders'],
            'open_count': report['open_orders'],
            'line_count': report['lines'],
            'quantity_total': sum(
                line['quantity'] or 0
                for order in report['mapped'] for line in order['lines']),
            'amount_total': report['total'],
            'isbn_count': len(report['isbns']),
            'matched_count': len(report['isbns']) - len(unmatched),
            'unmatched_isbns': "\n".join(unmatched) or False,
            'warnings': "\n\n".join(warnings) or False,
        })
        return self._reopen()

    def action_import(self):
        """Grava o espelho. Nenhuma cotação é criada, nada é confirmado."""
        self.ensure_one()
        if not self.payload_json:
            raise UserError(_("Read from Amazon first."))

        orders = json.loads(self.payload_json)
        result = self.env['liber.amazon.order']._sync_from_amazon(
            self.account_id, orders)
        self.account_id.last_import_date = self.date_to or fields.Datetime.now()

        return {
            'type': 'ir.actions.act_window',
            'name': _("Amazon Orders (%(created)s new, %(updated)s updated)",
                      created=result['created'], updated=result['updated']),
            'res_model': 'liber.amazon.order',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.account_id.id)],
        }

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
