# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import fields, models, _


class RunNoshelfWizard(models.TransientModel):
    """Settling a book the shelf does not have. The operator may run the
    CO without those titles; what was dropped becomes an activity on the
    CO's chatter, so the stock gets fixed instead of forgotten."""
    _name = 'consignment.run.noshelf.wizard'
    _description = 'Settle lines without shelf stock'

    settlement_id = fields.Many2one(
        'consignment.settlement', string='Consignment', required=True,
        ondelete='cascade')
    summary = fields.Text(string='Lines without shelf stock', readonly=True)

    def action_remove_and_run(self):
        """Drop the ghost settles, leave the fix-the-stock activity, run
        the rest."""
        self.ensure_one()
        st = self.settlement_id
        ghost = st.line_ids.filtered(
            lambda l: l.qty_reported > l.qty_on_shelf)
        excluded = [(l.product_id.display_name, l.qty_reported,
                     l.qty_on_shelf) for l in ghost]
        for line in ghost:
            if line.qty_replenish or line.qty_return:
                # the line still does honest work; only the settle goes.
                # Zeroing qty_reported recomputes qty_replenish (the
                # suggestion follows the sale) — put the typed value back.
                keep_replenish, keep_return = (line.qty_replenish,
                                               line.qty_return)
                line.qty_reported = 0
                line.write({'qty_replenish': keep_replenish,
                            'qty_return': keep_return})
            else:
                line.unlink()
        note = Markup('<p>%s</p><ul>%s</ul>') % (
            _('Titles removed from %s for lack of shelf stock — check '
              'the customer shelf:', st.name),
            Markup('').join(
                Markup('<li>%s — settle %s, shelf %s</li>') % (
                    escape(name), qty, shelf)
                for name, qty, shelf in excluded))
        st.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('Fix shelf stock: %s title(s) dropped from the '
                      'settle', len(excluded)),
            note=note,
            user_id=(st.user_id or self.env.user).id)
        return st.action_run()
