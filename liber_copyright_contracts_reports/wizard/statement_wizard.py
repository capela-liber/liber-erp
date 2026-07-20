# -*- coding: utf-8 -*-
import base64

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class EdlabRoyaltyStatementWizard(models.TransientModel):
    _name = "edlab.royalty.statement.wizard"
    _description = "Royalty Statement Wizard"

    partner_ids = fields.Many2many(
        "res.partner",
        string="Beneficiaries",
        required=True,
        domain=[("is_edlab_author", "=", True)],
    )
    date_to = fields.Date(
        string="End Date",
        required=True,
        default=fields.Date.context_today,
        help="End of the period covered by the statement: only royalties "
        "accrued up to this date are included.",
    )

    def action_print(self):
        self.ensure_one()
        report = self.env.ref(
            "liber_copyright_contracts_reports.action_report_royalty_statement"
        )
        # The ids have to travel INSIDE data, not only as the docids argument.
        # As soon as a report action carries `data`, the web client switches the
        # download URL from /report/pdf/<report>/<ids> to /report/pdf/<report>
        # ?options=... -- the ids are dropped, the report renders with no record
        # at all, and the user gets a blank page. Passing the period without
        # passing the ids alongside it is therefore a contradiction.
        return report.report_action(
            self.partner_ids,
            data={
                "date_to": fields.Date.to_string(self.date_to),
                "ids": self.partner_ids.ids,
                "model": "res.partner",
            },
        )

    def action_send(self):
        """Email each author their statement PDF and log everything.

        One message per author on their own chatter (which notifies them by
        email with the PDF attached), a note on each contract involved, and
        the author's last statement date stamped with the period end.
        """
        self.ensure_one()
        no_email = self.partner_ids.filtered(lambda p: not p.email)
        if no_email:
            raise UserError(
                _("Set an email address first for: %s")
                % ", ".join(no_email.mapped("display_name"))
            )
        # v17+: the first argument of _render_qweb_pdf is the REPORT (xmlid /
        # record / id), and the records come in res_ids. Passing the ids first
        # made Odoo try to look them up as a report reference.
        report_ref = "liber_copyright_contracts_reports.action_report_royalty_statement"
        report = self.env.ref(report_ref)
        template = self.env.ref(
            "liber_copyright_contracts_reports.mail_template_royalty_statement"
        )
        date_to = self.date_to
        for partner in self.partner_ids:
            statement = partner._edlab_royalty_statement(date_to=date_to)
            pdf_content, _dummy = report.sudo()._render_qweb_pdf(
                report_ref,
                res_ids=partner.ids,
                data={"date_to": fields.Date.to_string(date_to)},
            )
            attachment = self.env["ir.attachment"].create(
                {
                    "name": _("Royalty statement - %s - %s.pdf")
                    % (partner.name, fields.Date.to_string(date_to)),
                    "type": "binary",
                    "datas": base64.b64encode(pdf_content),
                    "res_model": "res.partner",
                    "res_id": partner.id,
                    "mimetype": "application/pdf",
                }
            )
            # The template reads the period and the net amount from the
            # rendering context (inline templates expose it as `ctx`).
            contextual_template = template.with_context(
                edlab_period_label=statement["period_label"],
                edlab_net_label=formatLang(
                    self.env, statement["net"], currency_obj=statement["currency"]
                ),
            )
            subject = contextual_template._render_field(
                "subject", partner.ids, compute_lang=True
            )[partner.id]
            body = contextual_template._render_field(
                "body_html", partner.ids, compute_lang=True
            )[partner.id]
            partner.message_post(
                subject=subject,
                body=body,
                partner_ids=partner.ids,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                attachment_ids=attachment.ids,
                email_layout_xmlid="mail.mail_notification_light",
            )
            partner.edlab_last_statement_date = date_to
            contracts = self.env["edlab.contract"].browse(
                {row["line"].contract_id.id for row in statement["rows"]}
            )
            for contract in contracts:
                contract.message_post(
                    body=_(
                        "Royalty statement (%s) sent to %s.",
                        statement["period_label"],
                        partner.display_name,
                    )
                )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Royalty statements"),
                "message": _("Statement sent to %s author(s).")
                % len(self.partner_ids),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
