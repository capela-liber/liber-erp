# -*- coding: utf-8 -*-
"""Tests for the consignment agreement lifecycle and the shelf-location
invariants (the CO root lives OUTSIDE the warehouse tree, so consigned stock
never pollutes native On Hand)."""
from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "soc_agreements")
class TestAgreements(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.product = cls.env["product.product"].create({
            "name": "Dom Casmurro", "type": "consu", "is_storable": True})

    def _agreement(self, name, activate=True):
        partner = self.env["res.partner"].create({
            "name": name, "is_company": True})
        agr = self.env["consignment.agreement"].create({
            "partner_id": partner.id,
            "company_id": self.company.id,
            "date_start": fields.Date.today(),
        })
        if activate:
            agr.action_activate()
        return agr

    def test_activation_creates_shelf_and_flags_partner(self):
        agr = self._agreement("Livraria Alfa")
        self.assertEqual(agr.state, "active")
        shelf = agr.location_id
        self.assertTrue(shelf, "activation must create the shelf location")
        self.assertTrue(shelf.is_consignment_shelf)
        self.assertEqual(shelf.usage, "internal")
        self.assertEqual(shelf.consignment_partner_id, agr.partner_id)
        self.assertTrue(agr.partner_id.allow_consignment)
        self.assertEqual(agr.partner_id.consignment_location_id, shelf)
        # idempotent: re-activating must not mint a second shelf
        agr.action_activate()
        self.assertEqual(agr.location_id, shelf)

    def test_shelf_root_lives_outside_the_warehouse(self):
        """The invariant that keeps consigned stock out of native On Hand."""
        agr = self._agreement("Livraria Beta")
        root = self.env["stock.location"]._soc_consignment_root(self.company)
        self.assertFalse(root.location_id,
                         "the CO root must be a top-level location")
        self.assertFalse(agr.location_id.warehouse_id,
                         "a shelf must not belong to any warehouse")

    def test_only_one_open_agreement_per_partner(self):
        agr = self._agreement("Livraria Gama")
        with self.assertRaises(ValidationError):
            self.env["consignment.agreement"].create({
                "partner_id": agr.partner_id.id,
                "company_id": self.company.id,
                "date_start": fields.Date.today(),
            })
        # a closed agreement does not block a new one
        agr.action_close()
        self.assertEqual(agr.state, "closed")
        second = self.env["consignment.agreement"].create({
            "partner_id": agr.partner_id.id,
            "company_id": self.company.id,
            "date_start": fields.Date.today(),
        })
        self.assertTrue(second)

    def test_cannot_close_with_stock_on_shelf(self):
        agr = self._agreement("Livraria Delta")
        self.env["stock.quant"]._update_available_quantity(
            self.product, agr.location_id, 5)
        with self.assertRaises(UserError):
            agr.action_close()
        # empty the shelf -> closing is allowed
        self.env["stock.quant"]._update_available_quantity(
            self.product, agr.location_id, -5)
        agr.action_close()
        self.assertEqual(agr.state, "closed")

    def test_resolve_for_prefers_open_agreement(self):
        agr = self._agreement("Livraria Épsilon")
        partner = agr.partner_id
        agr.action_close()
        reopened = self.env["consignment.agreement"].create({
            "partner_id": partner.id,
            "company_id": self.company.id,
            "date_start": fields.Date.today(),
        })
        resolved = self.env["consignment.agreement"]._resolve_for(
            partner, self.company)
        self.assertEqual(resolved, reopened,
                         "an open agreement must win over a closed one")
        # with none at all: empty recordset, no crash
        stranger = self.env["res.partner"].create({
            "name": "Sem Contrato", "is_company": True})
        self.assertFalse(self.env["consignment.agreement"]._resolve_for(
            stranger, self.company))
