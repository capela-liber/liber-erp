# -*- coding: utf-8 -*-
from odoo import api, fields, models


class GenerateWizard(models.TransientModel):
    """Confirmation wizard for the monthly "Gerar CO" batch.

    Like a "Run Scheduled Action", this batch touches many records at once, so
    it asks for a confirmation and shows the scope (how many open consignments,
    how many already have a draft CO and will be skipped, how many will be
    created) before the user commits.
    """
    _name = 'consignment.settlement.generate.wizard'
    _description = 'Generate Monthly Consignment Operations'

    open_count = fields.Integer(
        string='Open consignments', readonly=True)
    existing_draft_count = fields.Integer(
        string='Already draft (skipped)', readonly=True)
    to_create_count = fields.Integer(
        string='To create', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        Settlement = self.env['consignment.settlement']
        company = self.env.company
        agreements = self.env['consignment.agreement'].search([
            ('state', '=', 'active'),
            ('company_id', '=', company.id),
        ]).filtered(lambda a: a.on_shelf_qty > 0)
        existing = to_create = 0
        for agr in agreements:
            # The SAME rule the generation uses, on purpose. Two copies would
            # drift, and then the wizard would promise a number the batch does not
            # deliver -- the worst kind of lie a confirmation dialog can tell.
            if Settlement.search_count(
                    Settlement._blocking_draft_domain(agr.partner_id, company)):
                existing += 1
            else:
                to_create += 1
        res.update({
            'open_count': len(agreements),
            'existing_draft_count': existing,
            'to_create_count': to_create,
        })
        return res

    def action_confirm(self):
        self.ensure_one()
        return self.env['consignment.settlement'].generate_monthly_settlements()

    def action_view_drafts(self):
        """The way out when there is nothing to create: the operations already
        exist, in draft, waiting to be run. A dead-end dialog reads as a bug."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Operations to run'),
            'res_model': 'consignment.settlement',
            'domain': [('state', '=', 'draft'),
                       ('company_id', '=', self.env.company.id)],
            'view_mode': 'list,form',
        }
