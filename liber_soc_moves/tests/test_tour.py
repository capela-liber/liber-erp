# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestSocConsignmentTour(HttpCase):
    def test_soc_consignment_tour(self):
        """Drive the agreement lifecycle through the real UI: create ->
        Activate (the shelf is born) -> Close. Only the partner is seeded —
        the agreement itself is created BY the tour, on screen."""
        partner = self.env["res.partner"].create({
            "name": "Livraria do Tour", "is_company": True})

        self.start_tour("/odoo", "soc_consignment_tour", login="admin")

        agreement = self.env["consignment.agreement"].search(
            [("partner_id", "=", partner.id)], limit=1)
        self.assertTrue(agreement, "the tour must have created the agreement")
        self.assertEqual(agreement.state, "closed")
        self.assertTrue(agreement.location_id,
                        "activation must have created the shelf")
        self.assertTrue(agreement.location_id.is_consignment_shelf)
