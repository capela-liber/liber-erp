# -*- coding: utf-8 -*-
"""O rótulo da conferência chega em português.

Em 09/10/2026 o campo e o filtro "Location without document" apareceram em
inglês no prod: a tradução estava no .po, mas sem a linha de referência
(#: model:ir.model.fields,...), e o Odoo 19 só aplica tradução de rótulo de
campo e de view quando a referência existe."""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTraducao(TransactionCase):
    def setUp(self):
        super().setUp()
        if not self.env["res.lang"]._lang_get("pt_BR"):
            self.skipTest("pt_BR não está ativo neste banco")

    def test_rotulo_do_campo_em_portugues(self):
        field = self.env["ir.model.fields"]._get("edlab.contract", "location_missing")
        self.assertEqual(field.with_context(lang="pt_BR").field_description,
                         "Localização sem documento")

    def test_filtro_em_portugues(self):
        view = self.env.ref("liber_copyright_contracts_cloud.view_edlab_contract_search_cloud")
        arch = view.with_context(lang="pt_BR").arch_db
        self.assertIn("Localização sem documento", arch)
        self.assertNotIn("Location without document", arch)
