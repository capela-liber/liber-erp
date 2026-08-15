# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    allow_consignment = fields.Boolean(string='Allows Consignment')
    consignment_location_id = fields.Many2one(
        'stock.location', string='Consignment Shelf',
        help="Internal location holding our stock placed at this customer.")
    consignment_agreement_ids = fields.One2many(
        'consignment.agreement', 'partner_id', string='Consignment Agreements')
    consignment_agreement_count = fields.Integer(
        string='# Consignment Agreements',
        compute='_compute_consignment_agreement_count')

    def _soc_sales_channel(self, company=None):
        """The customer's sales channel, read in the DOCUMENT's company.

        The channel lives on `res.partner.team_id`, which the
        `liber_partner_commercial` module puts back (Odoo 19 removed it). This
        stack does NOT depend on that module -- a house that only consigns
        should not be forced to install it -- so the read is guarded, the same
        way `liber_nfe_xml` guards it.

        The field is `company_dependent`: the same customer may be of one
        channel in one publisher and another elsewhere, so the company matters
        and is never guessed.

        Falls back UP THE TREE, and not through `commercial_partner_id`: a
        branch with its own tax ID is `is_company`, so it is its own commercial
        partner and the shortcut would never reach the head office. The channel
        is a property of the ACCOUNT, so a branch with an empty card inherits
        from whoever it hangs from.
        """
        self.ensure_one()
        if 'team_id' not in self._fields:
            return self.env['crm.team']
        empresa = company or self.env.company
        no = self
        while no:
            canal = no.with_company(empresa).team_id
            if canal:
                return canal
            no = no.parent_id
        return self.env['crm.team']

    def _compute_consignment_agreement_count(self):
        groups = self.env['consignment.agreement']._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count'])
        counts = {partner.id: count for partner, count in groups}
        for partner in self:
            partner.consignment_agreement_count = counts.get(partner.id, 0)

    def action_view_consignment_agreements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consignment Agreements'),
            'res_model': 'consignment.agreement',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
