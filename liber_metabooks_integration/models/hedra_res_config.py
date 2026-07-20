from odoo import _, fields, models
from odoo.exceptions import ValidationError


class ResConfigInherit(models.TransientModel):
    _inherit = 'res.config.settings'

    metabooks_username = fields.Char()
    metabooks_password = fields.Char()
    metabooks_authorisation_code = fields.Char(readonly=True)
    # TODO v19 port: NCM. 'account.ncm' model absent in v19 community l10n_br.
    # ncm_product_code_new = fields.Many2one('account.ncm', string='Default NCM code')
    metabooks_ids = fields.Char(readonly=True)

    # Fields (of product.template) to publish on the website product page.
    # Note: ir.model.fields.modules is a non-stored computed field in v19 and cannot
    # be used in a search domain, so we only filter by model here.
    product_fields = fields.Many2many("ir.model.fields", string="Product Fields", domain=[('model', '=', 'product.template')])

    # get the values from System Parameter(saved values)
    def get_values(self):
        ks_res = super(ResConfigInherit, self).get_values()
        params = self.env['ir.config_parameter'].sudo()
        product_fields = params.get_param('metabooks_integration.product_fields') if params.get_param('metabooks_integration.product_fields') else '[]'
        ks_res.update(
            metabooks_username=params.get_param('metabooks_username'),
            metabooks_password=params.get_param('metabooks_password'),
            metabooks_authorisation_code=params.get_param('metabooks_authorisation_code'),
            # ncm_product_code_new=int(params.get_param('ncm_product_code_new')),  # TODO v19 port: NCM
            metabooks_ids=params.get_param('metabooks_ids'),
            product_fields=[(6, 0, eval(product_fields))],
        )
        return ks_res

    # get the values from Front and save values in system parameter
    def set_values(self):
        super(ResConfigInherit, self).set_values()
        self.env['ir.config_parameter'].sudo().set_param('metabooks_username', self.metabooks_username)
        self.env['ir.config_parameter'].sudo().set_param('metabooks_password', self.metabooks_password)
        # self.env['ir.config_parameter'].sudo().set_param('ncm_product_code_new', self.ncm_product_code_new.id)  # TODO v19 port: NCM
        self.env['ir.config_parameter'].sudo().set_param('metabooks_integration.product_fields', self.product_fields.ids)

    def action_test_metabooks_connection(self):
        """Save creds and verify we can authenticate against Metabooks."""
        self.set_values()
        self.env['metabooks.connector'].test_connection()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Metabooks'),
                'message': _('Connection successful.'),
                'sticky': False,
            },
        }

    def publish_product_fields(self):
        param = self.env['ir.config_parameter'].sudo()
        if param.get_param('metabooks_integration.product_fields'):
            custom_product_fields = eval(self.env['ir.config_parameter'].sudo().get_param('metabooks_integration.product_fields'))
            return custom_product_fields
            # custom_product_fields_names = []
            # for custom_field in custom_product_fields:
            #     product_fields = self.env['ir.model.fields'].sudo().browse(custom_field)
            #     if product_fields:
            #         custom_product_fields_names.append(product_fields.name)
            # return custom_product_fields_names

    def publish_product_label(self, fields):
        product_label = False
        if fields:
            product_fields = self.env['ir.model.fields'].sudo().browse(fields)
            product_label = product_fields.field_description if product_fields.field_description else product_fields.display_name
        return product_label

    def product_field_value(self, fields, product):
        product_value = False
        if fields:
            product_fields = self.env['ir.model.fields'].sudo().browse(fields)
            product_name = product_fields.name
            if product_name == 'isbn':
                product_name = 'default_code'
            # product_value = product.product_name
            query = """ select coalesce(%s) from product_template where id = %s
            """ % (product_name, product.id)
            self.env.cr.execute(query)
            product_value = self.env.cr.fetchall()
        return product_value[0][0]