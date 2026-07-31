# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    metabrasil_enabled = fields.Boolean(
        related='company_id.metabrasil_enabled', readonly=False)
    metabrasil_mode = fields.Selection(
        related='company_id.metabrasil_mode', readonly=False)
    metabrasil_api_url = fields.Char(
        related='company_id.metabrasil_api_url', readonly=False)
    metabrasil_test_api_url = fields.Char(
        related='company_id.metabrasil_test_api_url', readonly=False)
    metabrasil_access_key = fields.Char(
        related='company_id.metabrasil_access_key', readonly=False)
    metabrasil_username = fields.Char(
        related='company_id.metabrasil_username', readonly=False)
    metabrasil_password = fields.Char(
        related='company_id.metabrasil_password', readonly=False)
    metabrasil_partner_id = fields.Many2one(
        related='company_id.metabrasil_partner_id', readonly=False)
    metabrasil_warehouse_transport = fields.Selection(
        related='company_id.metabrasil_warehouse_transport', readonly=False)
    metabrasil_auto_validate_picking = fields.Boolean(
        related='company_id.metabrasil_auto_validate_picking', readonly=False)
    metabrasil_auto_create_bill = fields.Boolean(
        related='company_id.metabrasil_auto_create_bill', readonly=False)
    metabrasil_send_status_mails = fields.Boolean(
        related='company_id.metabrasil_send_status_mails', readonly=False)
    metabrasil_exception_activities = fields.Boolean(
        related='company_id.metabrasil_exception_activities', readonly=False)
    metabrasil_pricing_enabled = fields.Boolean(
        related='company_id.metabrasil_pricing_enabled', readonly=False)
    metabrasil_print_runs = fields.Char(
        related='company_id.metabrasil_print_runs', readonly=False)
    metabrasil_pod_tag_id = fields.Many2one(
        related='company_id.metabrasil_pod_tag_id', readonly=False)

    def action_metabrasil_refresh_prices(self):
        """Sweep the whole catalogue now, instead of waiting a fortnight.

        Hands the job to the cron rather than running it here: ~700 books at
        roughly a second each is several minutes, which no browser should be
        asked to hold. You get an answer immediately and the work happens
        behind you.
        """
        self.ensure_one()
        cron = self.env.ref('liber_metabrasil.ir_cron_metabrasil_prices',
                            raise_if_not_found=False)
        if not cron:
            raise UserError(_("The price sweep scheduled action is missing; "
                              "upgrade the module to restore it."))
        cron.sudo()._trigger()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': _("Metabrasil print prices"),
                'message': _(
                    "Sweep scheduled: it starts within the minute and runs in "
                    "the background. Follow it in Settings > Technical > "
                    "Scheduled Actions, or just check the books' Purchase tab "
                    "in a few minutes."),
                'sticky': False,
            },
        }

    def action_metabrasil_test_connection(self):
        """Ping Metabrasil with a read-only freight quote and report back.

        Tests the *saved* company settings, so save the form before clicking
        if the credentials were just edited. Nothing is ever posted.
        """
        self.ensure_one()
        result = self.env['metabrasil.api'].test_connection(self.company_id)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': result['level'],
                'title': _("Metabrasil connection"),
                'message': result['message'],
                'sticky': result['level'] != 'success',
            },
        }
