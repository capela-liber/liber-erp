# -*- coding: utf-8 -*-
from odoo import _, fields, models


class AccountMove(models.Model):
    """The accounting note of a bonus links BACK to its B000.

    The B000 already points to the note (note_move_id). The reverse was
    missing: from the note you could not reach the bonus that generated it -- a
    text ref ("B00190") is not a link. Now it is a real Many2one, so the vínculo
    is bidirectional and you can navigate either way.
    """
    _inherit = 'account.move'

    remessa_origin = fields.Selection(
        selection_add=[('bonus', "Bonificação")],
        ondelete={'bonus': 'set default'})

    bonus_id = fields.Many2one(
        'product.bonus', string="Bonus", readonly=True, copy=False, index=True,
        help="The bonus copy (B000) this note was generated for.")

    def action_open_bonus(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.bonus',
            'res_id': self.bonus_id.id,
            'view_mode': 'form',
        }
