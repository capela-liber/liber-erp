# -*- coding: utf-8 -*-
"""Two authors, three contracts (one author on two of them), an authors'
team with its alias, and a royalty accrued so the statement has a line."""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase


def make_fixture(cls):
    today = fields.Date.today()
    cls.company = cls.env.company
    cls.company.contract_authors_alias = "autores"
    cls.team = cls.company._edlab_authors_team()
    cls.author_a = cls.env["res.partner"].create({
        "name": "Autor da Missão", "email": "autor.a@example.org", "lang": "en_US"})
    cls.author_b = cls.env["res.partner"].create({
        "name": "Autora Beta", "email": "autor.b@example.org", "lang": "en_US"})
    cls.customer = cls.env["res.partner"].create({"name": "Livraria"})
    Product = cls.env["product.template"]
    cls.book1 = Product.create({"name": "Obra Um", "type": "consu", "list_price": 10.0})
    cls.book2 = Product.create({"name": "Obra Dois", "type": "consu", "list_price": 10.0})
    cls.book3 = Product.create({"name": "Obra Três", "type": "consu", "list_price": 10.0})

    def contract(author, book):
        c = cls.env["edlab.contract"].create({
            "signature_date": today - timedelta(days=30),
            "expiration_date": today + timedelta(days=365),
            "royalty_line_ids": [(0, 0, {
                "partner_id": author.id, "product_id": book.id,
                "tier_ids": [(0, 0, {"qty_from": 0, "qty_to": 0, "percentage": 10.0})],
            })],
        })
        c.royalty_line_ids.action_create_analytic_account()
        return c
    cls.c1 = contract(cls.author_a, cls.book1)
    cls.c2 = contract(cls.author_a, cls.book2)
    cls.c3 = contract(cls.author_b, cls.book3)
    # A sale of Obra Um, so author A's statement has a line.
    move = cls.env["account.move"].create({
        "move_type": "out_invoice", "partner_id": cls.customer.id,
        "invoice_date": today,
        "invoice_line_ids": [(0, 0, {
            "product_id": cls.book1.product_variant_id.id,
            "quantity": 10, "price_unit": 10.0})],
    })
    move.action_post()
    cls.c1.royalty_line_ids._book_royalties_from_invoices(move)
    cls.mission = cls.env["edlab.author.mission"].create({
        "name": "Prestação de contas 1S/2026", "kind": "statement",
        "date_to": today, "contract_ids": [(6, 0, [cls.c1.id, cls.c2.id, cls.c3.id])],
    })


class MissionCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        make_fixture(cls)
