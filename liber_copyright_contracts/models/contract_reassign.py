# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EdlabContractReassign(models.TransientModel):
    _name = "edlab.contract.reassign"
    _description = "Reassign Contract Responsible"

    user_id = fields.Many2one(
        "res.users",
        string="New Responsible",
        required=True,
    )
    contract_ids = fields.Many2many(
        "edlab.contract",
        string="Contracts",
        default=lambda self: self.env.context.get("active_ids", []),
    )

    def action_apply(self):
        self.ensure_one()
        contracts = self.contract_ids or self.env["edlab.contract"].browse(
            self.env.context.get("active_ids", [])
        )
        contracts.write({"user_id": self.user_id.id})
        return {"type": "ir.actions.act_window_close"}
