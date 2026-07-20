# -*- coding: utf-8 -*-
from odoo import fields, models, _


class RunOverstockWizard(models.TransientModel):
    _name = 'consignment.run.overstock.wizard'
    _description = 'Replenishment lines that exceed On Hand'

    settlement_id = fields.Many2one(
        'consignment.settlement', string='Consignment', required=True, ondelete='cascade')
    summary = fields.Text(string='Lines over On Hand', readonly=True)

    def action_remove_and_run(self):
        """Remove (zero the replenish of) the non-conforming lines, then run."""
        self.ensure_one()
        st = self.settlement_id
        over = st.line_ids.filtered(lambda l: l.qty_replenish > l.qty_on_hand)
        over.write({'qty_replenish': 0})
        return st.action_run()
