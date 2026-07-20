# -*- coding: utf-8 -*-
from odoo import fields, models

# O CFOP decide o documento. Três operações tiram o livro do armazém sem vender, e elas
# não são a mesma coisa -- misturá-las num mesmo Pedido C faria o mapa da consignação
# mentir, que é exatamente o que o sistema antigo faz.
DOCUMENT_BY_CFOP = {
    # consignação: o livro continua NOSSO, na prateleira do cliente
    '5917': 'consignment', '6917': 'consignment',
    # acerto: aqui, e só aqui, a consignação vira receita
    '5113': 'settlement', '6113': 'settlement',
    '5114': 'settlement', '6114': 'settlement',
    # devolução: o livro volta para o nosso armazém
    '1918': 'consignment_return', '2918': 'consignment_return',
    '5918': 'consignment_return', '6918': 'consignment_return',
    '1919': 'consignment_return', '2919': 'consignment_return',
    # bonificação: o livro é DADO. Sai do estoque, nunca vira receita.
    '5910': 'bonus', '6910': 'bonus',
    # feira/exposição: o livro viaja e VOLTA
    '5914': 'event_out', '6914': 'event_out',
    '1914': 'event_return', '2914': 'event_return',
    # venda comum
    '5101': 'sale', '6101': 'sale', '5102': 'sale', '6102': 'sale',
    # simples remessa: ambígua por natureza. Não decide sozinha -- um humano diz o que é.
    '5949': 'transfer', '6949': 'transfer',
}


def classify_cfops(env):
    """Aplica a regra por CÓDIGO, criando o CFOP que ainda não existir."""
    Cfop = env['nfe.cfop']
    for code, kind in DOCUMENT_BY_CFOP.items():
        cfops = Cfop.search([('code', '=', code)])
        if cfops:
            cfops.write({'document_kind': kind})
        else:
            Cfop.create({'code': code, 'document_kind': kind})


class NfeCfop(models.Model):
    """LAB FORK: minimal stand-in for the CFOP model that the production
    stack gets from l10n_br_eletronic_document. Same model name, so swapping
    the real localization back in keeps the data."""
    _name = "nfe.cfop"
    _description = "CFOP"
    _rec_name = "code"

    code = fields.Char(required=True, index=True)
    name = fields.Char(string="Description")

    # Lives HERE, with the model it belongs to, and not in soc_audit where it was
    # born: soc_settlement reads it (to rebuild a shelf from the fiscal history)
    # and soc_settlement does NOT depend on soc_audit -- soc_audit depends on IT.
    # The inverted dependency only ever worked because everything happened to be
    # loaded at runtime; it blew up the moment a stored field had to be computed
    # during soc_settlement's own module load, before soc_audit existed.
    # The classification data and the settings screen stay in soc_audit.
    consignment_effect = fields.Selection(
        selection=[
            ('ship', 'Shipment (+ shelf)'),
            ('sale', 'Effective sale (- shelf)'),
            ('return', 'Return / recall (- shelf)'),
            ('ignore', 'Ignore'),
        ],
        string='Consignment Effect',
        help="How an item carrying this CFOP moves the expected shelf balance "
             "when rebuilding it from the fiscal history:\n"
             "- Shipment: adds to the shelf (remessa em consignação).\n"
             "- Effective sale: removes from the shelf (venda efetivada).\n"
             "- Return / recall: removes from the shelf (devolução/retorno).\n"
             "- Ignore: not a consignment movement.\n"
             "Empty means the CFOP is not mapped -- its items land in the "
             "audit's 'unmapped CFOP' bucket.")

    # The CFOP decides the document. Three things leave the warehouse without a sale,
    # and they are NOT the same thing -- putting them all in a Pedido C would make the
    # consignment map lie, which is exactly what the old system does:
    #
    #   consignment (5917/6917)  the book is still OURS, on the customer's shelf.
    #                            It comes back, or it is settled (5113/6113).
    #   bonus       (5910/6910)  the book is GIVEN. It stops being ours: expense,
    #                            never revenue. No shelf, no settlement, no return.
    #   event       (5914/6914)  the book travels and COMES BACK to us (1914/2914).
    #                            A temporary transfer between our own locations.
    document_kind = fields.Selection(
        selection=[
            ('sale', 'Sale'),
            ('consignment', 'Consignment shipment (Pedido C)'),
            ('settlement', 'Consignment settlement (Acerto)'),
            ('consignment_return', 'Consignment return'),
            ('bonus', 'Bonus / gift (leaves stock, never revenue)'),
            ('event_out', 'To an event (comes back)'),
            ('event_return', 'Back from an event'),
            ('transfer', 'Plain shipment (undecided)'),
            ('other', 'Other'),
        ],
        string='Document',
        help="Which document this operation is, in Odoo. It is the CFOP that decides: "
             "a consignment shipment becomes a Pedido C (the goods stay ours, on the "
             "customer's shelf); a bonus is not a Pedido C at all (the goods are given "
             "away -- they leave the stock and never become revenue); an event shipment "
             "is an internal transfer that comes back. Empty means undecided, and the "
             "operation lands in the unmapped bucket instead of guessing.")

    def _compute_display_name(self):
        for cfop in self:
            cfop.display_name = "%s%s" % (
                cfop.code, " - %s" % cfop.name if cfop.name else "")
