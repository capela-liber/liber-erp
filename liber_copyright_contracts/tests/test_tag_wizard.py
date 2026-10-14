# -*- coding: utf-8 -*-
"""Mass tagging from the contracts list: add keeps what is there, remove
takes only the chosen tags off, replace leaves exactly the chosen ones --
and a contract not selected is never touched."""
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestContractTagWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        Contract = cls.env["edlab.contract"]
        cls.c1, cls.c2, cls.c3 = [Contract.create({
            "signature_date": today,
            "expiration_date": today + timedelta(days=365),
        }) for _ in range(3)]
        Tag = cls.env["edlab.contract.tag"]
        cls.tag_a = Tag.create({"name": "Campanha 2026"})
        cls.tag_b = Tag.create({"name": "Selo Hedra"})
        cls.c3.tag_ids = [(4, cls.tag_a.id)]

    def _run(self, contracts, tags, mode):
        wizard = self.env["edlab.contract.tag.wizard"].with_context(
            active_ids=contracts.ids, active_model="edlab.contract"
        ).create({"tag_ids": [(6, 0, tags.ids)], "mode": mode})
        self.assertEqual(wizard.contract_ids, contracts)
        res = wizard.action_apply()
        self.assertEqual(res["type"], "ir.actions.act_window_close")

    def test_add_remove_replace_and_untouched_third(self):
        selected = self.c1 | self.c2
        self._run(selected, self.tag_a | self.tag_b, "add")
        self.assertEqual(self.c1.tag_ids, self.tag_a | self.tag_b)
        self.assertEqual(self.c2.tag_ids, self.tag_a | self.tag_b)
        self.assertEqual(self.c3.tag_ids, self.tag_a)

        self._run(selected, self.tag_b, "remove")
        self.assertEqual(self.c1.tag_ids, self.tag_a)
        self.assertEqual(self.c2.tag_ids, self.tag_a)

        self._run(self.c1, self.tag_b, "replace")
        self.assertEqual(self.c1.tag_ids, self.tag_b)
        self.assertEqual(self.c2.tag_ids, self.tag_a)
        self.assertEqual(self.c3.tag_ids, self.tag_a)

    def test_add_is_idempotent(self):
        self._run(self.c3, self.tag_a, "add")
        self.assertEqual(self.c3.tag_ids, self.tag_a)
