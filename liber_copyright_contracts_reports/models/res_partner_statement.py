# -*- coding: utf-8 -*-
"""What the top of the statement prints: the address for the window, the
beneficiary's data, and how to pay. Kept apart from res_partner.py so the
fields and the printing evolve separately."""
import base64

from odoo import _, fields, models

# Money keys of the statement, top level and inside its row lists: what gets
# converted when the beneficiary is paid in another currency.
MONEY_KEYS = {
    "accrued", "advance_recouped", "total", "irrf", "net", "special_sales_total",
    "recoupable_advance_total", "non_recoupable_advance_total",
    "base", "amount", "recoupable", "non_recoupable", "amount_total",
    "amount_residual", "nominal", "corrected",
}
ROW_LISTS = ("rows", "advances", "special_sales", "bills", "legacy_years")
ROW_DICTS = ("legacy_years_total",)


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _edlab_royalty_statement(self, date_to=None):
        res = super()._edlab_royalty_statement(date_to=date_to)
        res["lang"] = self.env.context.get("lang") or self.lang or "pt_BR"
        res["header"] = self._edlab_statement_header()
        self._edlab_convert_statement(res)
        return res

    def _edlab_convert_statement(self, res):
        """Rewrite every money value of the statement in the beneficiary's
        currency, when it differs from the company's AND a rate exists for
        the period end. Without a rate the statement stays in the company
        currency and says so: a silent conversion at 1:1 would be a lie."""
        self.ensure_one()
        company = self.env.company
        target = self.sudo().edlab_beneficiary_currency_id
        source = res["currency"]
        if not target or target == source:
            return
        date = res.get("date_to") or fields.Date.context_today(self)
        rate_date = max(
            (r.name for r in target.rate_ids if r.name <= date), default=None)
        if not rate_date:
            res["fx_note"] = _(
                "Amounts in %(company)s: no exchange rate for %(currency)s is "
                "on file.", company=source.name, currency=target.name)
            return

        def convert(value):
            return target.round(source._convert(value, target, company, date))

        for key in MONEY_KEYS & set(res):
            if isinstance(res[key], (int, float)) and not isinstance(res[key], bool):
                res[key] = convert(res[key])
        for name in ROW_LISTS:
            for row in res.get(name) or []:
                for key in MONEY_KEYS & set(row):
                    if isinstance(row[key], (int, float)) and not isinstance(row[key], bool):
                        row[key] = convert(row[key])
        for name in ROW_DICTS:
            row = res.get(name) or {}
            for key in MONEY_KEYS & set(row):
                row[key] = convert(row[key])
        unit = source._convert(1.0, target, company, date)
        res["currency"] = target
        res["fx_note"] = _(
            "Amounts converted from %(source)s to %(target)s at the rate of "
            "%(date)s (1 %(source)s = %(unit).4f %(target)s).",
            source=source.name, target=target.name,
            date=self._edlab_statement_date_label(rate_date), unit=unit)

    def _edlab_address_lines(self):
        """The postal address in the few lines a window takes: name, street,
        complement, 'CEP city - state', and the country only when abroad."""
        self.ensure_one()
        lines = [self.name or "", self.street or "", self.street2 or ""]
        city = " ".join(part for part in (self.city, self.state_id.code) if part)
        lines.append(" ".join(part for part in (self.zip, city) if part))
        country = self.country_id
        if country and country != self.env.company.country_id:
            lines.append(country.name)
        return [line.strip() for line in lines if line and line.strip()]

    def _edlab_statement_header(self):
        """Address lines, window geometry, the identification rows and the
        payment rows the statement prints at the top.

        Sensitive fields (marital status, education, race) are manager-only;
        the statement is printed by any contracts user, so they are read as
        sudo here -- the print is the declared purpose of the data.
        """
        self.ensure_one()
        company = self.env.company
        me = self.sudo()
        def selection(record, field):
            """The translated label of a selection value, '' when unset."""
            value = record[field]
            return dict(record._fields[field]._description_selection(
                self.env)).get(value, "") if value else ""
        if me.is_company:
            identification = [
                (_("Legal name"), me.name),
                (_("Trade name"), me.edlab_trade_name if "edlab_trade_name" in me._fields else ""),
                (_("CNPJ"), me.vat),
                (_("State registration"), me.nfe_inscricao_estadual
                 if "nfe_inscricao_estadual" in me._fields else ""),
                (_("Municipal registration"), me.edlab_municipal_registration),
                (_("Collaborator"), me.edlab_legal_representative_id.name),
                (_("Head office"), ", ".join(me._edlab_address_lines()[1:])),
            ]
        else:
            birth = ""
            if me.edlab_birthdate:
                birth = me.edlab_birthdate.strftime("%d/%m/%Y")
                if me.edlab_birth_place:
                    birth += " (%s)" % me.edlab_birth_place
            identification = [
                (_("Full name"), me.name),
                (_("CPF"), me.vat),
                (_("RG"), me.edlab_rg),
                (_("PIS"), me.edlab_pis),
                (_("Birth"), birth),
                (_("Nationality"), me.edlab_nationality),
                (_("Marital status"), selection(me, "edlab_marital_status")),
                (_("Education"), selection(me, "edlab_education")),
                (_("Race/color"), selection(me, "edlab_race")),
                (_("Address"), ", ".join(me._edlab_address_lines()[1:])),
            ]
        identification.append((_("E-mail"), me.email))
        payment = []
        bank = me.bank_ids.sorted(lambda b: (not b.edlab_prefer_pix, b.sequence, b.id))[:1]
        if bank:
            pix = bank._edlab_pix_label()
            if bank.edlab_prefer_pix and pix:
                payment.append((_("Pix"), pix))
            payment += [
                (_("Bank"), bank.bank_id.name or bank.bank_name),
                (_("Agency"), bank.edlab_agency),
                (selection(bank, "edlab_account_kind") or _("Account"),
                 bank.acc_number),
            ]
            if pix and not bank.edlab_prefer_pix:
                payment.append((_("Pix"), pix))
        currency = me.edlab_beneficiary_currency_id
        if currency and currency != company.currency_id:
            payment.append((_("Currency"), currency.name))
        window = company._edlab_envelope_window()
        return {
            "address_lines": self._edlab_address_lines(),
            "window": window,
            "identification": [(k, v) for k, v in identification if v],
            "payment": [(k, v) for k, v in payment if v],
            "caption": _(
                "Envelope proof: window %(top)s mm from the top and %(left)s mm "
                "from the left of the sheet, %(width)s x %(height)s mm. Fold on "
                "the dotted lines, top panel outward.",
                top=company.edlab_envelope_window_top, left=window["left"],
                width=window["width"], height=window["height"]),
        }

    def _edlab_statement_pdf(self, date_to=None, for_email=False):
        """The statement of this beneficiary as PDF bytes, plus the dict it
        was built from. ``for_email`` drops the envelope-window address
        block; the printed version keeps it. Rendered for real even under
        the test runner: a print batch merges PDFs, not HTML."""
        self.ensure_one()
        report_ref = "liber_copyright_contracts_reports.action_report_royalty_statement"
        report = self.env.ref(report_ref).with_context(force_report_rendering=True)
        date_to = date_to or fields.Date.context_today(self)
        statement = self.with_context(
            lang=self.lang or self.env.lang or "pt_BR")._edlab_royalty_statement(date_to=date_to)
        pdf_content, _dummy = report.sudo()._render_qweb_pdf(
            report_ref, res_ids=self.ids,
            data={"date_to": fields.Date.to_string(date_to), "no_window": for_email})
        return statement, pdf_content

    def _edlab_statement_attachment(self, date_to=None, for_email=True):
        """The statement as an attachment on the contact, plus the statement
        dict. Used by the e-mail wizard and by the author missions: one
        place renders, two places send."""
        self.ensure_one()
        date_to = date_to or fields.Date.context_today(self)
        statement, pdf_content = self._edlab_statement_pdf(date_to, for_email=for_email)
        # sudo: the contracts people who send statements need not hold
        # write on the contact.
        attachment = self.env["ir.attachment"].sudo().create({
            "name": _("Royalty statement - %s - %s.pdf") % (
                self.name, fields.Date.to_string(date_to)),
            "type": "binary",
            "datas": base64.b64encode(pdf_content),
            "res_model": "res.partner",
            "res_id": self.id,
            "mimetype": "application/pdf",
        })
        return statement, attachment
