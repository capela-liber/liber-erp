# -*- coding: utf-8 -*-
from odoo import models

# The CFOP kinds that take a book out of the warehouse WITHOUT selling it. The
# module docstring of sale_order.py names three such operations, and they are
# all here: the consignment shipment (the book stays ours, on the customer's
# shelf), the bonus (the book is given -- expense, never revenue) and the fair
# (the book travels and comes back). A settlement and a plain sale are NOT
# here: those are the two documents that really are revenue.
#
# 'transfer' (5949/6949, a plain remessa) is here too, by his call of
# 19/08/2026: the CFOP is undecided about WHICH shipment it is, but it is a
# shipment -- nothing under 5949 ever was a sale.
#
# 'other' stays in, and so does the EMPTY kind: `document_kind` is derived from
# the CFOP, which the house only started filling recently, so every older order
# has it blank. Blank means "we don't know", not "not a sale" -- and filtering
# it out would empty the dashboard.
NOT_REVENUE_KINDS = ('consignment', 'consignment_return', 'bonus',
                     'event_out', 'event_return', 'transfer')


class SaleReport(models.Model):
    """A book that leaves without being sold never counts as a sale.

    liber_soc_moves already keeps the Pedido C out of every sale.report view by
    its flag. This is the other axis, the fiscal one: what the CFOP says the
    operation IS. A bonus (5910/6910) leaves stock and never becomes revenue,
    and a fair shipment (5914/6914) comes back -- neither is a sale, and neither
    can show up in a card, a chart or a table of sales.

    The NULL kind counts, and has to -- see the list above.
    """
    _inherit = 'sale.report'

    def _where_sale(self):
        kinds = ", ".join("'%s'" % kind for kind in NOT_REVENUE_KINDS)
        return super()._where_sale() + (
            " AND (s.document_kind IS NULL OR s.document_kind NOT IN (%s))" % kinds)
