# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class BudgetAnalytic(models.Model):
    _name = 'budget.analytic'
    _description = "Budget"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char(required=True, tracking=True)
    user_id = fields.Many2one(
        'res.users', string="Responsible",
        default=lambda self: self.env.user, tracking=True)
    date_from = fields.Date(string="Start Date", required=True, tracking=True)
    date_to = fields.Date(string="End Date", required=True, tracking=True)
    state = fields.Selection(
        selection=[
            ('draft', "Draft"),
            ('confirmed', "Open"),
            ('revised', "Revised"),
            ('done', "Done"),
            ('canceled', "Canceled"),
        ],
        string="Status", required=True, default='draft',
        readonly=True, copy=False, tracking=True)
    company_id = fields.Many2one(
        'res.company', string="Company", required=True,
        default=lambda self: self.env.company)
    group_id = fields.Many2one('budget.group', string="Group")
    tag_ids = fields.Many2many('budget.tag', string="Tags")
    parent_id = fields.Many2one(
        'budget.analytic', string="Revision Of",
        index=True, ondelete='cascade', copy=False)
    children_ids = fields.One2many(
        'budget.analytic', 'parent_id', string="Revisions")
    revision_count = fields.Integer(compute='_compute_revision_count')

    budget_line_ids = fields.One2many(
        'budget.line', 'budget_analytic_id', string="Budget Lines", copy=True)

    # ----------------------------------------------------------------
    # Computes / constraints
    # ----------------------------------------------------------------
    @api.depends('children_ids')
    def _compute_revision_count(self):
        for budget in self:
            budget.revision_count = len(budget.children_ids)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for budget in self:
            if budget.date_from and budget.date_to and budget.date_from > budget.date_to:
                raise ValidationError(_("The end date cannot be earlier than the start date."))

    @api.constrains('parent_id')
    def _check_parent_cycle(self):
        if self._has_cycle():
            raise ValidationError(_("You cannot create a recursive budget revision."))

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft_canceled(self):
        if any(budget.state not in ('draft', 'canceled') for budget in self):
            raise UserError(_("You can only delete budgets in Draft or Canceled state."))

    # ----------------------------------------------------------------
    # State actions
    # ----------------------------------------------------------------
    def action_confirm(self):
        for budget in self:
            budget.state = 'revised' if budget.children_ids else 'confirmed'

    def action_set_draft(self):
        self.state = 'draft'

    def action_cancel(self):
        self.state = 'canceled'

    def action_done(self):
        self.state = 'done'

    def action_create_revision(self):
        revisions = self.env['budget.analytic']
        for budget in self:
            revision = budget.copy({
                'name': _("%s (revision)", budget.name),
                'parent_id': budget.id,
            })
            budget.state = 'revised'
            revisions |= revision
        return {
            'type': 'ir.actions.act_window',
            'name': _("Budget Revision"),
            'res_model': 'budget.analytic',
            'view_mode': 'form',
            'res_id': revisions[:1].id,
            'target': 'current',
        }

    def action_open_revisions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Revisions"),
            'res_model': 'budget.analytic',
            'view_mode': 'list,form',
            'domain': [('parent_id', '=', self.id)],
        }

    @api.model
    def _demo_post_moves(self, move_xmlids):
        """Helper p/ a demo data postar os lançamentos de exemplo."""
        for xmlid in move_xmlids:
            move = self.env.ref(xmlid, raise_if_not_found=False)
            if move and move.state == 'draft':
                move.action_post()
