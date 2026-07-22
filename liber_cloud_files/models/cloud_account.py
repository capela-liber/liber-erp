# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class LiberCloudAccount(models.Model):
    """One company, one provider, one credential.

    The storages have a single account per company -- the company's
    account -- and Odoo decides who acts through it. Multicompany starts
    here: each company plugs its own credential, and every folder resolves
    its account by (provider, company).
    """
    _name = 'liber.cloud.account'
    _description = 'Cloud Storage Account'
    _order = 'company_id, provider'

    provider = fields.Selection(
        selection=[], required=True,
        help="Which storage this credential opens. Provider modules add "
             "their entry here.")
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    share_ttl_days = fields.Integer(
        string='Shared Links Expire After (days)', default=30,
        help="Every shared link created from Odoo dies after this many "
             "days; sharing again renews the deadline. 0 creates links "
             "that never expire. Providers that cannot expire links "
             "ignore or refuse this -- each manual says which.")
    active = fields.Boolean(default=True)

    _provider_company_uniq = models.Constraint(
        'unique(provider, company_id)',
        'This company already has an account for this provider.')

    @api.depends('provider', 'company_id')
    def _compute_display_name(self):
        selection = dict(self._fields['provider'].get_description(
            self.env)['selection'])
        for record in self:
            record.display_name = '%s — %s' % (
                selection.get(record.provider, record.provider or '?'),
                record.company_id.name or '?')

    def _client(self):
        self.ensure_one()
        return self.env['liber.cloud.provider']._client(self)

    def action_test_connection(self):
        self.ensure_one()
        info = self._client().check()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Connected"),
                'message': _(
                    "Authenticated as %(name)s (%(email)s).",
                    name=info.get('name', '?'), email=info.get('email', '?')),
                'sticky': False,
            },
        }
