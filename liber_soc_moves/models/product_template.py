# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


def _drop_repeated_code(display_name, code):
    """Show the ISBN once, even when the name already carries it.

    Legacy imports baked the ISBN into ``product.template.name`` itself
    ("[9788577152063] Habitar (...)", and also "ebook - [9788577152063] ...").
    Odoo then prefixes ``default_code`` again when building ``display_name``,
    so the code shows up twice: "[9788577152063] [9788577152063] Habitar".

    This drops the repeat at DISPLAY time only -- the stored name is left
    untouched, so nothing is lost and the fix survives re-imports. Products
    whose name is already clean keep Odoo's single prefix.
    """
    if not code or not display_name:
        return display_name
    marker = '[%s] ' % code
    if not display_name.startswith(marker):
        # No prefix from Odoo (display_default_code=False, or the formatted
        # "name\t--code--" shape): whatever the name carries is the only copy.
        return display_name
    # Keep Odoo's prefix, drop the copy baked into the name.
    return marker + display_name[len(marker):].replace(marker, '', 1)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _compute_display_name(self):
        super()._compute_display_name()
        for tmpl in self:
            tmpl.display_name = _drop_repeated_code(
                tmpl.display_name, tmpl.default_code)

    soc_qty_wh = fields.Integer(
        string='Stock', compute='_compute_soc_qty',
        help="Our own stock on hand in the main stock location. Consignment "
             "shelves live outside the warehouse, so they count neither here "
             "nor in the native On Hand.")
    soc_qty_consigned = fields.Integer(
        string='Consigned', compute='_compute_soc_qty',
        help="Units currently placed on customers' consignment shelves.")

    def _compute_soc_qty(self):
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        Quant = self.env['stock.quant']
        for tmpl in self:
            vids = tmpl.product_variant_ids.ids
            wh_qty = cons_qty = 0.0
            if vids:
                if warehouse:
                    whq = Quant.search([
                        ('product_id', 'in', vids),
                        ('location_id', 'child_of', warehouse.lot_stock_id.id),
                        ('quantity', '!=', 0),
                    ])
                    wh_qty = sum(whq.mapped('quantity'))
                cq = Quant.search([
                    ('product_id', 'in', vids),
                    ('location_id.is_consignment_shelf', '=', True),
                    ('quantity', '!=', 0),
                ])
                cons_qty = sum(cq.mapped('quantity'))
            tmpl.soc_qty_wh = int(round(wh_qty))
            tmpl.soc_qty_consigned = int(round(cons_qty))

    def _soc_quant_action(self, name, domain):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'stock.quant',
            'view_mode': 'list',
            'domain': domain,
            'context': {'search_default_groupby_location': 1},
        }

    def action_view_soc_wh_stock(self):
        self.ensure_one()
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        return self._soc_quant_action(_('Stock'), [
            ('product_id', 'in', self.product_variant_ids.ids),
            ('location_id', 'child_of', warehouse.lot_stock_id.id),
            ('quantity', '!=', 0),
        ])

    def action_view_soc_consigned(self):
        self.ensure_one()
        # Reuse the Consigned Stock views (list/pivot/graph, grouped by customer):
        # from a product the question is always "who is holding my books?", and
        # grouping by customer also folds together the shelves of a customer who
        # happens to have more than one agreement.
        action = self.env['ir.actions.actions']._for_xml_id(
            'liber_soc_moves.action_consigned_stock')
        action['display_name'] = _('Consigned Stock')
        action['domain'] = [
            ('product_id', 'in', self.product_variant_ids.ids),
            ('location_id.is_consignment_shelf', '=', True),
            ('quantity', '!=', 0),
        ]
        return action


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _compute_display_name(self):
        super()._compute_display_name()
        for product in self:
            product.display_name = _drop_repeated_code(
                product.display_name, product.default_code)
