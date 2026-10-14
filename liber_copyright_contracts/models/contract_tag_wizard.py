# -*- coding: utf-8 -*-
"""Tag many contracts at once from the list: the renewal campaign, the
imprint, the author mission to come. Mirrors the reassign wizard."""
from odoo import fields, models


class EdlabContractTagWizard(models.TransientModel):
    _name = "edlab.contract.tag.wizard"
    _description = "Tag Contracts"

    contract_ids = fields.Many2many(
        "edlab.contract",
        string="Contracts",
        default=lambda self: self.env.context.get("active_ids", []),
    )
    tag_ids = fields.Many2many(
        "edlab.contract.tag",
        string="Tags",
        required=True,
    )
    mode = fields.Selection(
        [("add", "Add"), ("remove", "Remove"), ("replace", "Replace")],
        string="Mode",
        required=True,
        default="add",
        help="Add keeps the tags the contracts already have; Remove takes "
        "only these off; Replace leaves exactly these.",
    )

    def action_apply(self):
        self.ensure_one()
        contracts = self.contract_ids or self.env["edlab.contract"].browse(
            self.env.context.get("active_ids", [])
        )
        if self.mode == "replace":
            commands = [(6, 0, self.tag_ids.ids)]
        else:
            code = 4 if self.mode == "add" else 3
            commands = [(code, tag.id) for tag in self.tag_ids]
        contracts.write({"tag_ids": commands})
        return {"type": "ir.actions.act_window_close"}
