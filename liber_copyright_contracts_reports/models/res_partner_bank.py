# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    edlab_agency = fields.Char(
        string="Agency",
        help="Bank branch (agência) printed on the royalty statement.",
    )
    edlab_account_kind = fields.Selection(
        [("checking", "Checking"), ("savings", "Savings")],
        string="Account Kind", default="checking")
    edlab_pix_key_type = fields.Selection(
        [("cpf", "CPF"), ("cnpj", "CNPJ"), ("email", "E-mail"),
         ("phone", "Phone"), ("random", "Random key")],
        string="Pix Key Type")
    edlab_pix_key = fields.Char(string="Pix Key")
    edlab_prefer_pix = fields.Boolean(
        string="Pay by Pix",
        help="The beneficiary prefers Pix over a bank transfer: the "
        "statement shows the Pix key first.")

    @api.constrains("edlab_pix_key", "edlab_pix_key_type", "edlab_prefer_pix")
    def _check_pix(self):
        for bank in self:
            key = (bank.edlab_pix_key or "").strip()
            kind = bank.edlab_pix_key_type
            if bool(key) != bool(kind):
                raise ValidationError(_(
                    "A Pix key needs both the key and its type."))
            if bank.edlab_prefer_pix and not key:
                raise ValidationError(_(
                    "To pay by Pix, enter the Pix key first."))
            if kind == "email" and "@" not in key:
                raise ValidationError(_("A Pix e-mail key needs an '@'."))
            if kind in ("cpf", "cnpj", "phone"):
                digits = re.sub(r"\D", "", key)
                expected = {"cpf": 11, "cnpj": 14}.get(kind)
                if expected and len(digits) != expected:
                    raise ValidationError(_(
                        "A %(kind)s Pix key has %(n)s digits.",
                        kind=kind.upper(), n=expected))
                if kind == "phone" and not 10 <= len(digits) <= 13:
                    raise ValidationError(_(
                        "A phone Pix key has 10 to 13 digits (with area and "
                        "country code)."))

    def _edlab_pix_label(self):
        """'CPF 123.456.789-00' or '' -- for the statement and the list."""
        self.ensure_one()
        if not self.edlab_pix_key:
            return ""
        label = dict(self._fields["edlab_pix_key_type"]._description_selection(
            self.env)).get(self.edlab_pix_key_type, "")
        return "%s %s" % (label, self.edlab_pix_key)
