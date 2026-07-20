from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class MetabooksProductTemplate(models.Model):
    _inherit = 'product.template'

    # Warning for duplication of barcode
    @api.onchange('barcode')
    def metabooks_product_barcode(self):
        for rec in self:
            if rec.barcode:
                product_ids = self.search([('barcode', '=', rec.barcode)])
                if product_ids:
                    self.update({
                        'barcode': ''
                    })
                    return {'warning': {'title': _("Warning"),
                                        'message': _("This Barcode * %s * is Already exists!! "
                                                     % (rec.barcode))
                                        }
                            }
