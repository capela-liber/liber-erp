# -*- coding: utf-8 -*-
import re

from odoo import fields, models

# Original statement palette, used when the company has no document-layout
# primary color to derive the table colors from.
WINE_PALETTE = {
    "header_text": "#fdf3f1",
    "header": "#7a3033",
    "header_dark": "#5c2327",
    "header_light": "#a1554b",
    "row": "#f7efee",
    "row_light": "#fdfaf9",
}


class RoyaltyStatementReport(models.AbstractModel):
    _name = "report.liber_copyright_contracts_reports.report_royalty_statement"
    # O nome derivado de _name passa dos 63 caracteres do Postgres depois do
    # prefixo liber_. É AbstractModel: a tabela nunca é criada, só validada.
    _table = "royalty_statement_report"
    _description = "Royalty Statement Report"

    def _statement_colors(self):
        """Table palette derived from the company's document-layout primary
        color (Settings > Configure Document Layout), so the statement follows
        the branding chosen there. Falls back to the original wine palette
        when the company has no (valid) primary color."""
        primary = self.env.company.primary_color or ""
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", primary):
            return dict(WINE_PALETTE)

        def mix(color, target, ratio):
            channels = (int(color[i:i + 2], 16) for i in (1, 3, 5))
            return "#%02x%02x%02x" % tuple(
                round(c + (t - c) * ratio) for c, t in zip(channels, target)
            )

        white, black = (255, 255, 255), (0, 0, 0)
        return {
            "header_text": mix(primary, white, 0.93),
            "header": primary,
            "header_dark": mix(primary, black, 0.25),
            "header_light": mix(primary, white, 0.28),
            "row": mix(primary, white, 0.94),
            "row_light": mix(primary, white, 0.985),
        }

    def _get_report_values(self, docids, data=None):
        # Each statement covers the royalties accrued since the author's last
        # payment up to the period end date (``date_to``, defaults to today).
        data = data or {}
        date_to = data.get("date_to")
        if date_to:
            date_to = fields.Date.to_date(date_to)
        # When the report action carries `data`, the web client requests the PDF
        # WITHOUT the ids in the URL, so `docids` arrives empty and the page
        # comes out blank. Recover them from where they do survive.
        docids = docids or data.get("ids") or self.env.context.get("active_ids") or []
        partners = self.env["res.partner"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "res.partner",
            "docs": partners,
            "colors": self._statement_colors(),
            "statements": {
                partner.id: partner._edlab_royalty_statement(date_to=date_to)
                for partner in partners
            },
        }
