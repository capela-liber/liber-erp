# -*- coding: utf-8 -*-
"""The authors' mailbox. The support engine needs a 'team' to own an alias
and route e-mails; the royalties department never meets that word. The
company keeps the alias name, and the team behind it is created and kept
in step here, out of sight."""
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    contract_authors_alias = fields.Char(
        string="Authors' mailbox", default="autores",
        help="Local part of the e-mail the authors write to and reply to "
        "(the domain is the company's alias domain): autores@... . "
        "Missions send from it; replies land on the author's ticket.")
    contract_support_team_id = fields.Many2one(
        "liber.support.team", string="Authors mailbox (team)",
        help="The support engine's record behind the authors' mailbox. "
        "Created and kept in step automatically.")

    def write(self, vals):
        res = super().write(vals)
        if "contract_authors_alias" in vals:
            for company in self.filtered("contract_support_team_id"):
                company._edlab_sync_authors_team()
        return res

    def _edlab_sync_authors_team(self):
        self.ensure_one()
        team = self.contract_support_team_id.sudo()
        alias = (self.contract_authors_alias or "").strip() or False
        if team and team.alias_name != alias:
            team.alias_name = alias

    def _edlab_authors_team(self):
        """The team behind this company's authors' mailbox, created on first
        use. Named after the mailbox, not after a desk."""
        self.ensure_one()
        team = self.sudo().contract_support_team_id
        if not team or not team.active:
            Team = self.env["liber.support.team"].sudo()
            team = Team.search([("company_id", "=", self.id),
                                ("name", "=", "Autores")], limit=1)
            if not team:
                team = Team.create({
                    "name": "Autores", "company_id": self.id,
                    "alias_name": (self.contract_authors_alias or "autores").strip() or False,
                })
            self.sudo().contract_support_team_id = team
        return team
