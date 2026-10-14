# -*- coding: utf-8 -*-
"""O relatório declara o tipo do livro na frente da obra (14/10/2026):
"pbook \u2014 Título". A forma ONIX da Metabooks decide; sem ela, o nome."""
from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_copyright_contracts_reports.models.res_partner import (
    edlab_book_type, edlab_work_label)


@tagged("post_install", "-at_install")
class TestBookType(TransactionCase):
    def _book(self, name, form=None):
        vals = {"name": name, "type": "consu"}
        if form:
            if "metabooks_product_form" not in self.env["product.template"]._fields:
                self.skipTest("sem a Metabooks neste banco")
            vals["metabooks_product_form"] = form
        return self.env["product.template"].create(vals)

    def test_form_decides(self):
        """Caminho feliz: a forma ONIX dá o tipo e o rótulo leva o travessão."""
        self.assertEqual(edlab_book_type(self._book("Dom Casmurro", "BC")), "pbook")
        self.assertEqual(edlab_book_type(self._book("Dom Casmurro", "EA")), "ebook")
        self.assertEqual(edlab_book_type(self._book("Dom Casmurro", "AA")), "abook")
        self.assertEqual(edlab_work_label(self._book("Dom Casmurro", "BC")),
                         "pbook \u2014 Dom Casmurro")

    def test_name_speaks_without_form(self):
        """Edge: sem forma, o nome do produto diz."""
        self.assertEqual(edlab_book_type(self._book("Dagon (audiolivro)")), "abook")
        self.assertEqual(edlab_book_type(self._book("Necropolítica (e-book)")), "ebook")

    def test_unknown_declares_nothing(self):
        """Erro evitado: sem forma e sem pista, não se inventa tipo."""
        book = self._book("Contos clássicos de vampiro")
        self.assertEqual(edlab_book_type(book), "")
        self.assertEqual(edlab_work_label(book), "Contos clássicos de vampiro")
        self.assertEqual(edlab_work_label(self.env["product.template"]), "")
