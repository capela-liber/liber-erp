# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    # `auto_invoice_id` is the OCA field on the mirror pointing at its source.
    # This is the other direction: the source seeing its mirror(s). sudo on
    # read because the mirror lives in the other company, which the current
    # user may not have active right now; the count must not depend on that.
    mirror_move_ids = fields.One2many(
        "account.move", "auto_invoice_id", string="Mirror Documents",
        readonly=True,
    )
    mirror_count = fields.Integer(
        string="Mirror Count", compute="_compute_mirror_count",
    )

    @api.depends("mirror_move_ids")
    def _compute_mirror_count(self):
        counts = {}
        if self.ids:
            groups = self.env["account.move"].sudo()._read_group(
                [("auto_invoice_id", "in", self.ids)],
                ["auto_invoice_id"], ["__count"],
            )
            counts = {src.id: count for src, count in groups}
        for move in self:
            move.mirror_count = counts.get(move.id, 0)

    def action_open_mirror(self):
        """The mirror(s) of this document, in the sister company."""
        self.ensure_one()
        mirrors = self.env["account.move"].sudo().search(
            [("auto_invoice_id", "=", self.id)])
        return self._liber_open_moves(mirrors, _("Mirror of %s", self.name))

    def action_open_mirror_source(self):
        """The document this mirror was created from."""
        self.ensure_one()
        source = self.sudo().auto_invoice_id
        return self._liber_open_moves(source, _("Source of %s", self.name))

    def _liber_open_moves(self, moves, name):
        action = {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "account.move",
            "context": {"create": False},
        }
        if len(moves) == 1:
            action.update({"view_mode": "form", "res_id": moves.id})
        else:
            action.update({"view_mode": "list,form",
                           "domain": [("id", "in", moves.ids)]})
        return action
