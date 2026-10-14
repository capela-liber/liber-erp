# -*- coding: utf-8 -*-
"""The author's folder is the contact card: every ticket, any mission."""
from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    edlab_support_ticket_ids = fields.One2many(
        "liber.support.ticket", "partner_id", string="Support tickets")
    edlab_support_ticket_count = fields.Integer(
        compute="_compute_edlab_support_ticket_count")

    def _compute_edlab_support_ticket_count(self):
        Ticket = self.env["liber.support.ticket"]
        counts = {
            partner.id: count for partner, count in Ticket._read_group(
                [("partner_id", "in", self.ids)], ["partner_id"], ["__count"])
        } if self.ids else {}
        for partner in self:
            partner.edlab_support_ticket_count = counts.get(partner.id, 0)

    def action_new_author_ticket(self):
        """A spontaneous ticket for this author: a call, a letter, a visit.
        Same team, same folder as the mission tickets."""
        self.ensure_one()
        team = self.env.company._edlab_authors_team()
        return {
            "type": "ir.actions.act_window", "name": _("New ticket"),
            "res_model": "liber.support.ticket", "view_mode": "form",
            "context": {
                "default_partner_id": self.id,
                "default_email_from": self.email,
                "default_team_id": team.id,
                "default_kind": "royalties",
                "default_edlab_contract_ids": [(6, 0, self.edlab_royalty_line_ids.contract_id.ids)],
            },
        }

    def action_view_author_tickets(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("liber_copyright_contracts_support.action_author_ticket")
        action["domain"] = [("partner_id", "=", self.id)]
        team = self.env.company._edlab_authors_team()
        action["context"] = {"default_partner_id": self.id, "default_kind": "royalties",
                             "default_email_from": self.email, "default_team_id": team.id,
                             "default_edlab_contract_ids": [(6, 0, self.edlab_royalty_line_ids.contract_id.ids)]}
        return action
