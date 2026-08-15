# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Credentials live on the company (five publishing houses run in parallel,
    # each with its own Metabrasil account), surfaced in Settings via related
    # fields. The O15 connector kept them here too -- one of the few designs
    # worth keeping.
    metabrasil_enabled = fields.Boolean(
        string='Metabrasil PoD',
        help="Master switch: when off, purchase orders to the printer are "
             "ordinary purchase orders -- nothing is sent, no cron touches "
             "them, no freight is quoted.")
    metabrasil_mode = fields.Selection(
        [('test', 'Testing'), ('production', 'Production')],
        string='Metabrasil Mode', default='test',
        help="Testing points every call at the sandbox URL below. Switch to "
             "Production only when the account manager confirms the access "
             "key is live.")
    metabrasil_api_url = fields.Char(
        string='Production API URL',
        help="Base URL of the live Metabrasil API (without the /pedidos "
             "path).")
    metabrasil_test_api_url = fields.Char(
        string='Sandbox API URL',
        help="Base URL of the Metabrasil sandbox, used while Mode is "
             "Testing.")
    metabrasil_access_key = fields.Char(
        string='Access Key (Metabrasil)',
        help="The chaveCliente Metabrasil issued for this company; rides "
             "inside every request body.")
    metabrasil_username = fields.Char(string='API Username')
    metabrasil_password = fields.Char(string='API Password')
    metabrasil_partner_id = fields.Many2one(
        'res.partner', string='Printer Partner',
        help="The Metabrasil vendor record. A purchase order is a print "
             "order exactly when its vendor is this partner (and the switch "
             "above is on).")

    # -- behaviour knobs -------------------------------------------------
    metabrasil_warehouse_transport = fields.Selection(
        [('meta_car', 'Metabrasil delivers (CARRO META)'),
         ('pickup', 'We pick up (RETIRADA)')],
        string='Warehouse Leg', default='meta_car',
        help="How warehouse-bound print runs travel: Metabrasil's own car "
             "drops them at our depot, or we fetch them at the plant.")
    metabrasil_auto_validate_picking = fields.Boolean(
        string='Auto-validate Receipts', default=True,
        help="When Metabrasil reports Shipped/Delivered, validate the "
             "receipt automatically with their reported weight and volume "
             "count. Off = the warehouse clicks Validate as usual.")
    metabrasil_auto_create_bill = fields.Boolean(
        string='Auto-draft Vendor Bill', default=False,
        help="When a print order is Shipped, draft (never post) the vendor "
             "bill from the purchase order. The O15 connector posted bills "
             "on its own; accounting asked it to stop.")
    metabrasil_send_status_mails = fields.Boolean(
        string='Customer Status E-mails', default=True,
        help="E-mail the customer of a direct-delivery print order when it "
             "enters production and when it is delivered.")
    metabrasil_exception_activities = fields.Boolean(
        string='Overdue Print Alerts', default=True,
        help="Daily sweep: print orders not approved within a day, not "
             "shipped by their scheduled date or not delivered by their "
             "expected date raise an activity for the buyer.")
    metabrasil_pricing_enabled = fields.Boolean(
        string='Production Pricing API', default=False,
        help="Query /pod-api/precificacao for the production cost ladder in "
             "the print quote wizard. Leave off until Metabrasil ships the "
             "endpoint; the wizard shows freight either way.")

    # -- print-price ladder ----------------------------------------------
    metabrasil_print_runs = fields.Char(
        string='Print Runs Quoted', default='1,15,40,100',
        help="Print runs asked of the pricing API, comma separated. Each one "
             "becomes a vendor-price line (min_qty) on every printable book, "
             "so the Odoo picks the right price by quantity on its own. "
             "Commercial decision -- change it here, not in the code.")
    metabrasil_pod_tag_id = fields.Many2one(
        'product.tag', string='Print-on-Demand Tag',
        help="Tag stamped on books the printer quotes, and removed when it "
             "stops quoting them. The API cannot be asked 'is this book in "
             "your catalogue?' -- a price coming back IS the answer, and this "
             "tag is where that answer is stored so you can filter on it.")

    @api.model
    def _metabrasil_set_default_pod_tag(self):
        """Point every company at the shipped PoD tag on install.

        A default= on the field cannot reference an XML id, and leaving it
        empty would make the sweep silently skip tagging.
        """
        tag = self.env.ref('liber_metabrasil.product_tag_pod',
                           raise_if_not_found=False)
        if tag:
            self.search([('metabrasil_pod_tag_id', '=', False)]
                        ).metabrasil_pod_tag_id = tag.id

    def _metabrasil_print_run_list(self):
        """'1,15,40,100' -> [1, 15, 40, 100]; junk entries are dropped."""
        self.ensure_one()
        runs = []
        for chunk in (self.metabrasil_print_runs or '').split(','):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                value = int(chunk)
            except ValueError:
                continue
            if value > 0 and value not in runs:
                runs.append(value)
        return sorted(runs)

    def _get_metabrasil_url(self):
        """Base URL for the current mode; empty string = not configured."""
        self.ensure_one()
        if not self.metabrasil_enabled:
            return ''
        if self.metabrasil_mode == 'production':
            return self.metabrasil_api_url or ''
        return self.metabrasil_test_api_url or ''
