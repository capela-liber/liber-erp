# -*- coding: utf-8 -*-
from odoo import _, fields, models


class EdlabContract(models.Model):
    _inherit = "edlab.contract"

    edlab_support_ticket_ids = fields.Many2many(
        "liber.support.ticket", "liber_support_ticket_contract_rel",
        "contract_id", "ticket_id", string="Support tickets")
    edlab_support_ticket_count = fields.Integer(
        compute="_compute_edlab_support_ticket_count")

    def _compute_edlab_support_ticket_count(self):
        for contract in self:
            contract.edlab_support_ticket_count = len(contract.edlab_support_ticket_ids)

    def action_view_support_tickets(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("liber_copyright_contracts_support.action_author_ticket")
        action["domain"] = [("edlab_contract_ids", "in", self.ids)]
        action["context"] = {"default_edlab_contract_ids": [(6, 0, self.ids)],
                             "default_kind": "royalties"}
        return action

    def action_new_mission(self):
        """From the contracts list: a mission over the selected contracts."""
        return {
            "type": "ir.actions.act_window", "name": _("New mission"),
            "res_model": "edlab.author.mission", "view_mode": "form",
            "context": {"default_contract_ids": [(6, 0, self.ids)]},
        }
