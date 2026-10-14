# -*- coding: utf-8 -*-
"""The ticket learns about contracts: which mission opened it and which
contracts it is about. Both answer the royalties department's question
from the two sides -- 'everything with this author' is the partner, 'what
was said about this contract' is the contract."""
from odoo import api, fields, models


class LiberSupportTicket(models.Model):
    _inherit = "liber.support.ticket"

    kind = fields.Selection(selection_add=[("royalties", "Royalties")],
                            ondelete={"royalties": "set default"})
    edlab_mission_id = fields.Many2one(
        "edlab.author.mission", string="Mission", index=True,
        ondelete="set null",
        help="The mission that opened this ticket, when it was not spontaneous.")
    edlab_contract_ids = fields.Many2many(
        "edlab.contract", "liber_support_ticket_contract_rel",
        "ticket_id", "contract_id", string="Contracts",
        help="The contracts this conversation is about.")
    edlab_author_answered = fields.Boolean(
        string="Author answered", compute="_compute_edlab_author_answered",
        help="The author wrote back after the ticket's first message.")

    edlab_contract_count = fields.Integer(compute="_compute_edlab_contract_count")

    @api.depends("edlab_contract_ids")
    def _compute_edlab_contract_count(self):
        for ticket in self:
            ticket.edlab_contract_count = len(ticket.edlab_contract_ids)

    @api.onchange("partner_id", "kind")
    def _onchange_partner_contracts(self):
        """A royalties ticket on an author starts with the author's
        contracts: the link is there before anyone types it."""
        if self.kind == "royalties" and self.partner_id and not self.edlab_contract_ids:
            self.edlab_contract_ids = self.partner_id.edlab_royalty_line_ids.contract_id

    def action_view_edlab_contracts(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "liber_copyright_contracts.action_edlab_contract")
        contracts = self.edlab_contract_ids
        if len(contracts) == 1:
            action.update({"res_id": contracts.id, "view_mode": "form", "views": [(False, "form")]})
        else:
            action["domain"] = [("id", "in", contracts.ids)]
        return action

    def action_view_edlab_author(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "res_model": "res.partner",
            "res_id": self.partner_id.id, "view_mode": "form", "views": [(False, "form")],
        }

    @api.depends("message_ids.author_id", "message_ids.message_type", "partner_id")
    def _compute_edlab_author_answered(self):
        Message = self.env["mail.message"].sudo()
        for ticket in self:
            partner = ticket.partner_id
            ticket.edlab_author_answered = bool(partner) and bool(
                Message.search_count([
                    ("model", "=", "liber.support.ticket"),
                    ("res_id", "=", ticket.id),
                    ("author_id", "=", partner.id),
                    ("message_type", "in", ("email", "comment")),
                ]))

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """A spontaneous e-mail on the authors' alias is a royalties ticket."""
        ticket = super().message_new(msg_dict, custom_values=custom_values)
        team = ticket.team_id
        if team and team == team.company_id.sudo().contract_support_team_id:
            # The authors' mailbox: a royalties ticket, whoever wrote.
            ticket.kind = "royalties"
        return ticket
