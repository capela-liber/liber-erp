# -*- coding: utf-8 -*-
"""Shared setup: an author, a work, a valid contract with a 10% copies tier
and a 40% licensing share, and its analytic account. No demo data."""
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import Form


class LicensingCommon:
    @classmethod
    def _setup_licensing(cls):
        today = fields.Date.today()
        cls.company = cls.env.company
        cls.author = cls.env["res.partner"].create({"name": "Patativa do Assaré"})
        cls.licensee = cls.env["res.partner"].create({"name": "Editora Didática"})
        cls.customer = cls.env["res.partner"].create({"name": "Livraria Cliente"})
        cls.book = cls.env["product.template"].create({
            "name": "Cante lá que eu canto cá", "type": "consu", "list_price": 10.0})
        cls.income = cls.env["account.account"].create({
            "name": "Receita de licenciamento",
            "code": "LIC4001",
            "account_type": "income",
            "company_ids": [Command.link(cls.company.id)],
        })
        cls.company.contract_license_account_id = cls.income
        cls.contract = cls.env["edlab.contract"].create({
            "signature_date": today - timedelta(days=60),
            "expiration_date": today + timedelta(days=365),
            "royalty_line_ids": [Command.create({
                "partner_id": cls.author.id,
                "product_id": cls.book.id,
                "license_percentage": 40.0,
                "tier_ids": [Command.create({
                    "qty_from": 0, "qty_to": 0, "percentage": 10.0})],
            })],
        })
        cls.royalty = cls.contract.royalty_line_ids
        cls.royalty.action_create_analytic_account()
        cls.account = cls.royalty.analytic_account_id

    # -- helpers --------------------------------------------------------
    def _licence_form(self, contract=None):
        contract = contract or self.contract
        return Form(self.env["account.move"].with_context(
            default_move_type="out_invoice",
            default_edlab_license_contract_id=contract.id))

    def _new_licence(self, amount=1000.0, invoice_date=None, post=True, pay=True):
        """A licence the way the screen makes it: New from the contract's
        list, licensee and amount typed, everything else from defaults."""
        form = self._licence_form()
        form.partner_id = self.licensee
        form.invoice_date = invoice_date or fields.Date.today()
        with form.invoice_line_ids.edit(0) as line:
            line.price_unit = amount
            line.tax_ids.clear()
        move = form.save()
        if post:
            move.action_post()
        if post and pay:
            self._pay(move)
        return move

    def _pay(self, move):
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=move.ids,
        ).create({})._create_payments()
        self.assertIn(move.payment_state, ("paid", "in_payment"))

    def _sell(self, qty, price=10.0):
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.customer.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [Command.create({
                "product_id": self.book.product_variant_id.id,
                "quantity": qty,
                "price_unit": price,
                "tax_ids": [Command.clear()],
            })],
        })
        move.action_post()
        self._pay(move)
        return move

    def _licence_entries(self):
        return self.env["account.analytic.line"].sudo().search(
            [("edlab_license_royalty_line_id", "=", self.royalty.id)])
