# -*- coding: utf-8 -*-
"""Shared fixture: two companies of the database wired for the OCA mirror,
a shared product, and an invoice from one to the other.

Companies of the database are reused when two of them have sale and
purchase journals; otherwise a sister is created with the same chart of
accounts loaded (the pattern of liber_copyright_contracts_intercompany), so
the suite runs on a one-company test database too.
"""
from odoo import fields


class MirrorFixture:
    """Mixin used by both the ORM and the tour tests."""

    def _two_companies(self):
        companies = self.env["res.company"].search([], order="id")
        usable = companies.filtered(lambda c: (
            self.env["account.journal"].search_count(
                [("company_id", "=", c.id), ("type", "=", "sale")])
            and self.env["account.journal"].search_count(
                [("company_id", "=", c.id), ("type", "=", "purchase")])
        ))
        if len(usable) < 2:
            # A seeded test database has one company. Borrow the pattern of
            # liber_copyright_contracts_intercompany: create the sister and
            # load the same chart, which brings its sale and purchase journals.
            base = usable[:1] or companies[:1]
            sister = self.env["res.company"].create(
                {"name": "Sister Company (mirror test)"})
            self.env["account.chart.template"].try_loading(
                base.chart_template, company=sister, install_demo=False)
            usable = base | sister
        return usable[0], usable[1]

    def _wire(self, source, dest):
        (source | dest).write({
            "intercompany_invoicing": True,
            "invoice_auto_validation": False,
        })
        self.env.user.company_ids |= source | dest
        product = self.env["product.product"].create({
            "name": "Mirror Link Test Product", "type": "service",
            "list_price": 100.0, "company_id": False,
        })
        return product

    def _post_pair(self, source, dest, product):
        invoice = self.env["account.move"].with_company(source).create({
            "move_type": "out_invoice",
            "company_id": source.id,
            "partner_id": dest.partner_id.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [(0, 0, {
                "product_id": product.id, "quantity": 1, "price_unit": 100.0})],
        })
        invoice.action_post()
        mirror = self.env["account.move"].sudo().search(
            [("auto_invoice_id", "=", invoice.id)])
        return invoice, mirror
