# -*- coding: utf-8 -*-
from odoo import Command, api, models

# Demo sales of the demo books: (invoice date, customer xmlid,
# [(book template xmlid, quantity)]). Quantities are chosen to cross the
# royalty tiers of demo/books_demo.xml (e.g. Hamlet passes 5000 copies, so
# the later sales accrue at 10% instead of 8%), and Dom Quixote stays below
# its advance so one account shows an advance still being recouped.
DEMO_BOOK_SALES = [
    ("2023-11-05", "base.res_partner_2",
     [("liber_copyright_contracts_reports.book_hamlet", 3000)]),
    ("2024-03-10", "base.res_partner_12",
     [("liber_copyright_contracts_reports.book_iliada", 1800),
      ("liber_copyright_contracts_reports.book_odisseia", 800)]),
    ("2024-08-01", "base.res_partner_3",
     [("liber_copyright_contracts_reports.book_crime", 2200)]),
    ("2024-09-15", "base.res_partner_2",
     [("liber_copyright_contracts_reports.book_iliada", 1500)]),
    ("2025-02-18", "base.res_partner_12",
     [("liber_copyright_contracts_reports.book_hamlet", 2500)]),
    ("2025-04-12", "base.res_partner_12",
     [("liber_copyright_contracts_reports.book_crime", 2300),
      ("liber_copyright_contracts_reports.book_quixote", 600)]),
    ("2025-09-30", "base.res_partner_2",
     [("liber_copyright_contracts_reports.book_orgulho", 1200)]),
]

DEMO_REF = "DEMO-LIVROS"


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model
    def _edlab_load_demo_book_sales(self):
        """Demo helper (called from demo/books_invoices_demo.xml).

        Creates, posts and pays customer invoices selling the demo books,
        then creates the analytic accounts of every royalty line and books
        the royalties, so a demo database shows the contract analytics
        populated out of the box. Done in Python because the automatically
        created product variants of the demo books have no XML id to
        reference from data files.

        Idempotent: the invoices are only created once (module updates
        reload demo files); account creation and booking are idempotent
        by themselves and re-run to catch up.
        """
        if self.search_count([("ref", "=", DEMO_REF)]):
            invoices = self.browse()
        else:
            invoices = self.create(
                [
                    {
                        "move_type": "out_invoice",
                        "partner_id": self.env.ref(customer).id,
                        "invoice_date": date,
                        "ref": DEMO_REF,
                        "invoice_line_ids": [
                            Command.create(
                                {
                                    "product_id": self.env.ref(
                                        book
                                    ).product_variant_id.id,
                                    "quantity": qty,
                                }
                            )
                            for book, qty in lines
                        ],
                    }
                    for date, customer, lines in DEMO_BOOK_SALES
                ]
            )
            invoices.action_post()
            for invoice in invoices:
                wizard = (
                    self.env["account.payment.register"]
                    .with_context(
                        active_model="account.move", active_ids=invoice.ids
                    )
                    .create({"payment_date": invoice.invoice_date})
                )
                wizard.action_create_payments()
        royalty_lines = self.env["edlab.contract.royalty.line"].search(
            [("product_id", "!=", False), ("partner_id", "!=", False)]
        )
        royalty_lines.action_create_analytic_account()
        self.env["edlab.contract"].search([]).action_fill_royalty_lines()
        return invoices
