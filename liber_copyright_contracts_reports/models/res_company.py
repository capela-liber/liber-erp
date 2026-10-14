# -*- coding: utf-8 -*-
"""The window envelope, as the company measures it.

Defaults (14/10/2026) come from the house's envelope, 230 x 115 mm with
the window about 15 mm from the bottom, 42 mm tall, starting 38 mm from
the left. The sheet folded in three (210 x 99) floats inside it by up to
16 mm vertically and 20 mm horizontally, so the address block is placed in
the strip the window shows WHATEVER the packet's position: 57 to 85 mm from
the top of the sheet, from 40 mm in. The house's 52 mm letterhead fits above.

The statement goes by post in a window envelope (115 x 230 mm, the A4
folded in three). Where the window falls on the sheet is a measurement of
the envelope the house buys, not something the code can know; the company
types it here, in millimetres from the sheet's top-left corner, and prints
an envelope proof to calibrate.

The letterhead must stay above the window: the statement therefore prints
with its own paper format, whose top margin is the "header height" below.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

PAPERFORMAT_XMLID = "liber_copyright_contracts_reports.paperformat_royalty_statement"


class ResCompany(models.Model):
    _inherit = "res.company"

    edlab_envelope_window_top = fields.Float(
        string="Window top (mm)", default=57.0, digits=(6, 1),
        help="Distance from the top edge of the A4 sheet to the top of the "
        "envelope window, with the sheet folded in three and the top panel "
        "facing the window.")
    edlab_envelope_window_left = fields.Float(
        string="Window left (mm)", default=40.0, digits=(6, 1),
        help="Distance from the left edge of the sheet to the left of the window.")
    edlab_envelope_window_width = fields.Float(
        string="Window width (mm)", default=95.0, digits=(6, 1))
    edlab_envelope_window_height = fields.Float(
        string="Window height (mm)", default=28.0, digits=(6, 1))
    edlab_statement_header_height = fields.Float(
        string="Letterhead height (mm)", default=52.0, digits=(6, 1),
        help="Top margin of the statement's paper format: the letterhead is "
        "drawn in it, and the page body (where the address block is placed) "
        "starts below it. Must be smaller than the window top.")

    @api.constrains("edlab_envelope_window_top", "edlab_envelope_window_left",
                    "edlab_envelope_window_width", "edlab_envelope_window_height",
                    "edlab_statement_header_height")
    def _check_envelope_window(self):
        for company in self:
            values = (company.edlab_envelope_window_top,
                      company.edlab_envelope_window_left,
                      company.edlab_envelope_window_width,
                      company.edlab_envelope_window_height,
                      company.edlab_statement_header_height)
            if any(v < 0 for v in values):
                raise UserError(_("Envelope measurements cannot be negative."))
            if company.edlab_envelope_window_top + company.edlab_envelope_window_height > 99:
                raise UserError(_(
                    "The window must fit the top panel of the folded sheet "
                    "(99 mm): top %(top)s + height %(height)s exceeds it.",
                    top=company.edlab_envelope_window_top,
                    height=company.edlab_envelope_window_height))

    def write(self, vals):
        res = super().write(vals)
        if "edlab_statement_header_height" in vals:
            self._edlab_sync_statement_paperformat()
        return res

    def _edlab_sync_statement_paperformat(self):
        """The statement's paper format follows the letterhead height.
        One format for the database: companies share it, and the last one
        written wins -- the house prints on the same letterhead anyway."""
        paperformat = self.env.ref(PAPERFORMAT_XMLID, raise_if_not_found=False)
        if not paperformat:
            return
        height = self[-1:].edlab_statement_header_height or 52.0
        paperformat.sudo().write({
            "margin_top": height,
            "header_spacing": max(height - 2.0, 0.0),
        })

    def _edlab_envelope_window(self):
        """The window in BODY coordinates (mm from the body's top-left), or a
        UserError when the letterhead would cover it."""
        self.ensure_one()
        header = self.edlab_statement_header_height
        top = self.edlab_envelope_window_top - header
        if top < 0:
            raise UserError(_(
                "The envelope window (%(top)s mm from the top) is covered by the "
                "letterhead (%(header)s mm). Lower the letterhead height in "
                "Settings > Copyright > Envelope.",
                top=self.edlab_envelope_window_top, header=header))
        return {
            "top": round(top, 1),
            "left": round(self.edlab_envelope_window_left, 1),
            "width": round(self.edlab_envelope_window_width, 1),
            "height": round(self.edlab_envelope_window_height, 1),
            # Fold lines, in body coordinates, for the envelope proof.
            "folds": [round(99.0 - header, 1), round(198.0 - header, 1)],
        }
