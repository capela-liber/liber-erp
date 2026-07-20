# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    """O CFOP decide o documento.

    Três operações tiram o livro do armazém sem vender, e elas não são a mesma coisa:

        consignação (5917/6917)  o livro continua nosso, na prateleira do cliente;
        bonificação (5910/6910)  o livro é dado -- sai do estoque, nunca vira receita;
        feira       (5914/6914)  o livro viaja e volta (1914/2914).

    Meter as três no mesmo Pedido C faria o mapa da consignação mentir: o consignado
    aumentaria com livros que foram doados, e o acerto cobraria por eles.
    """
    _inherit = 'sale.order'

    cfop_id = fields.Many2one(
        'nfe.cfop', string='CFOP', copy=False, index=True,
        help="A operação fiscal desta saída. É ela que decide que documento isto é.")
    document_kind = fields.Selection(
        related='cfop_id.document_kind', store=True, string='Operation',
        help="Derivado do CFOP. Vazio = indefinido: ninguém adivinha.")

    # --- a trava do meio-termo -------------------------------------------
    #
    # "Uma C000 não pode usar outra posição fiscal que a de consignação."
    # Trava dura resolveria, mas uma exceção legítima (regime especial,
    # substituição tributária) viraria chamado para o desenvolvedor. Então:
    # default aplicado, campo VISÍVEL para quem emite conferir antes da nota, e
    # editável só por quem tem responsabilidade fiscal na casa.
    consignment_fiscal_locked = fields.Boolean(
        compute='_compute_consignment_fiscal_locked',
        help="A posição fiscal deste pedido é ditada pela operação de "
             "consignação. Só o Administrador de faturamento pode trocá-la.")

    @api.depends('consignment_operation_id')
    def _compute_consignment_fiscal_locked(self):
        # has_group uma vez, não por registro: é o mesmo usuário na lista toda.
        pode_editar = self.env.user.has_group('account.group_account_manager')
        for order in self:
            order.consignment_fiscal_locked = (
                bool(order.consignment_operation_id) and not pode_editar)

    @api.onchange('cfop_id')
    def _onchange_cfop_id(self):
        """O CFOP manda: quem é consignação vira Pedido C, quem não é, não."""
        for order in self:
            if order.cfop_id.document_kind == 'consignment':
                order.is_consignment = True
                order.consignment_type = order.consignment_type or 'opening'
            elif order.cfop_id.document_kind in ('bonus', 'event_out', 'event_return'):
                order.is_consignment = False
                order.consignment_type = False

    @api.constrains('cfop_id', 'is_consignment')
    def _check_cfop_matches_document(self):
        for order in self:
            # read it from the CFOP itself: document_kind is a stored related field and
            # has not necessarily been recomputed when the constraint runs
            kind = order.cfop_id.document_kind
            if not kind:
                continue
            if kind == 'consignment' and not order.is_consignment:
                raise UserError(_(
                    "%(order)s carries CFOP %(cfop)s, a consignment shipment: the books "
                    "stay ours, on the customer's shelf. It has to be a Pedido C.",
                    order=order.name, cfop=order.cfop_id.code))
            if kind in ('bonus', 'event_out', 'event_return') and order.is_consignment:
                rotulo = dict(
                    order.cfop_id._fields['document_kind'].selection).get(kind, kind)
                raise UserError(_(
                    "%(order)s carries CFOP %(cfop)s (%(kind)s) and cannot be a Pedido C.\n\n"
                    "A bonus is given away -- it leaves the stock and never becomes "
                    "revenue. An event shipment comes back to us. Neither belongs on a "
                    "customer's consignment shelf, and neither is ever settled.",
                    order=order.name, cfop=order.cfop_id.code, kind=rotulo))

    # ------------------------------------------------------------------
    # A nota do Pedido C: uma remessa (REM/), nunca uma fatura
    # ------------------------------------------------------------------
    remessa_note_move_id = fields.Many2one(
        'account.move', string="Remessa note", readonly=True, copy=False)
    # The number, never the state: a remessa note can only be posted, so
    # "Lançado" under the button said nothing. The REM/ number says where to
    # look in Remessas; "A emitir" says there is nothing yet.
    remessa_note_label = fields.Char(
        compute='_compute_remessa_note_label', string="Note")

    @api.depends('remessa_note_move_id.name')
    def _compute_remessa_note_label(self):
        for order in self:
            order.remessa_note_label = (
                order.remessa_note_move_id.name or "A emitir")

    def action_generate_remessa_note(self):
        """The consignment shipment's fiscal note -- also a remessa.

        "Precisamos pensar na nota fiscal de consignação, que é também uma
        remessa." The Criar-fatura path on a Pedido C dead-ends by design (a
        consignment is not a sale; there is nothing to invoice), which left
        the C000 with NO note at all. This is the note: an out_invoice in the
        REM/ journal, under the CONSIGNMENT fiscal position from Settings --
        the field that sat unread since it was declared -- auto-settled on
        post, so the bookseller is never billed for books still ours.
        """
        for order in self:
            if not order.is_consignment:
                raise UserError(_(
                    "%s is not a Pedido C -- a regular sale invoices through "
                    "Criar fatura.", order.name))
            if order.state != 'sale':
                raise UserError(_(
                    "%s: confirm the Pedido first, then generate the note.",
                    order.name))
            if order.remessa_note_move_id:
                continue
            company = order.company_id
            fpos = company.consignment_shipment_fiscal_position_id
            if not (fpos and fpos.auto_invoice_paid
                    and fpos.auto_invoice_paid_account_id):
                raise UserError(_(
                    "The consignment shipment fiscal position is not mapped "
                    "(it needs Auto Invoice Paid and its account). Set it in "
                    "Settings > Consignment Fiscal -- a remessa de consignação "
                    "(CFOP 5917/6917) must never bill the bookseller."))
            note = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'journal_id': company._get_remessa_journal().id,
                'partner_id': order.partner_id.id,
                'fiscal_position_id': fpos.id,
                'invoice_date': fields.Date.context_today(order),
                'invoice_origin': order.name,
                'remessa_origin': 'consignment',
                'invoice_line_ids': [
                    (0, 0, {
                        'product_id': line.product_id.id,
                        'quantity': line.product_uom_qty,
                        'price_unit': line.price_unit,
                        'discount': line.discount,
                    })
                    for line in order.order_line
                    if not line.display_type
                ],
            })
            note.action_post()
            order.remessa_note_move_id = note
        return True

    def action_view_remessa_note(self):
        self.ensure_one()
        if not self.remessa_note_move_id:
            raise UserError(_(
                "%s has no remessa note yet. Generate it with the "
                "\"Gerar nota\" button after confirming.", self.name))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.remessa_note_move_id.id,
            'view_mode': 'form',
        }

    def _create_invoices(self, grouped=False, final=False, date=None):
        # A bonificação e a remessa para feira também não faturam: uma é doação, a
        # outra é transferência. O Pedido C já é barrado no soc_moves.
        nao_fatura = self.filtered(
            lambda o: o.document_kind in ('bonus', 'event_out', 'event_return'))
        if nao_fatura:
            raise UserError(_(
                "These orders do not invoice: %(orders)s.\n\n"
                "A bonus is a gift -- it is an expense, never revenue. An event "
                "shipment is a transfer between our own locations, and it comes back.",
                orders=", ".join(nao_fatura.mapped('name')),
            ))
        return super()._create_invoices(grouped=grouped, final=final, date=date)
