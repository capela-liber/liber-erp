# -*- coding: utf-8 -*-
"""Credential-safe tests for the Metabooks sync.

These NEVER touch the real API and NEVER need a username/password. The whole
HTTP layer is mocked at one seam: ``metabooks.connector._get_client`` is
patched to return a fake client, so no ``ir.config_parameter`` credential is
read and no network call is made. What we assert is the parsing + upsert: given
a known API payload, the right product.template fields get written.

For a REAL sync against a live publisher (e.g. BR0089701), see the manual smoke
test documented in the module description (Apps → Metabooks → Module Info).
"""
from unittest.mock import MagicMock, patch

from odoo.addons.liber_metabooks_integration.models import (
    metabooks_import_job as job_mod,
)
from odoo.tests import TransactionCase, tagged


# One ONIX "by ISBN" payload, trimmed to the keys the parser actually reads.
ONIX_BOOK = {
    "identifiers": [{"productIdentifierType": "03", "idValue": "9788599296264"}],
    "titles": [{"title": "O Cortiço", "subtitle": "edição comentada"}],
    "prices": [{"priceType": "02", "priceAmount": 59.90}],
    "textContents": [{"textType": "03", "text": "Romance naturalista brasileiro."}],
    "subjects": [
        {"subjectSchemeIdentifier": "20", "subjectHeadingText": "literatura"},
        {"subjectSchemeIdentifier": "20", "subjectHeadingText": "brasil"},
    ],
    "publisherData": {"name": "Editora Teste", "shortName": "ET", "mvbId": "BR0089701"},
}

# Two catalogue-feed items, as returned when importing a whole publisher (VL).
FEED_ITEMS = [
    {
        "isbn": "9788500000017",
        "title": "Livro A",
        "priceBrl": 30.0,
        "publisher": "Editora Teste",
        "publisherMbId": "BR0089701",
        "mainDescription": "Descrição A",
    },
    {
        "isbn": "9788500000024",
        "title": "Livro B",
        "priceBrl": 42.5,
        "publisher": "Editora Teste",
        "publisherMbId": "BR0089701",
        "mainDescription": "Descrição B",
    },
]


@tagged("post_install", "-at_install")
class TestMetabooksSync(TransactionCase):
    def _connector_with_fake(self, fake):
        """Return the connector with its _get_client patched to `fake`."""
        connector = self.env["metabooks.connector"]
        patcher = patch.object(type(connector), "_get_client", return_value=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return connector

    def test_import_isbn_creates_product_with_mapped_fields(self):
        """A by-ISBN import maps the ONIX payload onto product.template."""
        fake = MagicMock()
        fake.get_product_by_isbn.return_value = ONIX_BOOK
        connector = self._connector_with_fake(fake)

        res = connector.import_isbns(["978-85-99296-26-4"])  # hyphens are cleaned

        self.assertEqual(res["created"], 1)
        self.assertEqual(res["updated"], 0)
        self.assertEqual(res["not_found"], [])
        product = res["products"]
        self.assertEqual(len(product), 1)
        self.assertEqual(product.default_code, "9788599296264")
        self.assertEqual(product.barcode, "9788599296264")
        self.assertAlmostEqual(product.list_price, 59.90, places=2)
        self.assertEqual(product.metabooks_book_title, "O Cortiço")
        self.assertEqual(product.metabooks_book_subtitle, "edição comentada")
        self.assertEqual(product.synopsys, "Romance naturalista brasileiro.")
        self.assertEqual(product.metabooks_publisher, "Editora Teste")
        self.assertEqual(product.metabooks_vendor_id, "BR0089701")
        self.assertEqual(product.metabooks_keywords, "literatura, brasil")
        # the fake was used instead of any real client / credential
        fake.get_product_by_isbn.assert_called_once_with("9788599296264")

    def test_import_isbn_is_idempotent(self):
        """Re-importing the same ISBN updates, never duplicates."""
        fake = MagicMock()
        fake.get_product_by_isbn.return_value = ONIX_BOOK
        connector = self._connector_with_fake(fake)

        first = connector.import_isbns(["9788599296264"])
        second = connector.import_isbns(["9788599296264"])

        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["updated"], 1)
        self.assertEqual(first["products"], second["products"])
        matches = self.env["product.template"].search(
            [("default_code", "=", "9788599296264")])
        self.assertEqual(len(matches), 1)

    def test_import_isbn_not_found(self):
        """A 404 (client returns None) is reported, no product created."""
        fake = MagicMock()
        fake.get_product_by_isbn.return_value = None
        connector = self._connector_with_fake(fake)

        res = connector.import_isbns(["9788500000031"])

        self.assertEqual(res["created"], 0)
        self.assertEqual(res["not_found"], ["9788500000031"])
        self.assertFalse(res["products"])

    def test_import_publisher_catalogue(self):
        """Importing a publisher (VL / mvbId, e.g. BR0089701) walks its feed."""
        fake = MagicMock()
        fake.iter_publisher_products.return_value = iter(FEED_ITEMS)
        connector = self._connector_with_fake(fake)

        products = connector.import_publisher("BR0089701", with_covers=False)

        self.assertEqual(len(products), 2)
        self.assertEqual(
            set(products.mapped("default_code")),
            {"9788500000017", "9788500000024"},
        )
        self.assertTrue(all(p.metabooks_vendor_id == "BR0089701" for p in products))
        fake.iter_publisher_products.assert_called_once()

    # ------------------------------------------------------------------ #
    #  A página do catálogo contra um banco imperfeito                    #
    # ------------------------------------------------------------------ #
    def _fake_page(self, itens, total_pages=1):
        fake = MagicMock()
        fake.catalog_page.return_value = {
            "content": itens, "totalPages": total_pages,
            "totalElements": len(itens),
        }
        return self._connector_with_fake(fake)

    def test_upsert_escolhe_a_ficha_que_tem_o_barcode(self):
        """Com ISBN repetido em duas fichas, vale a que segura o barcode.

        A migração deixou pares assim: mesma referência interna, só uma com
        barcode. Gravar na outra esbarraria na unicidade do barcode.
        """
        Product = self.env["product.template"]
        isbn = FEED_ITEMS[0]["isbn"]
        sombra = Product.create({"name": "Sombra sem barcode", "default_code": isbn})
        verdadeira = Product.create(
            {"name": "Ficha de verdade", "default_code": isbn, "barcode": isbn})
        connector = self._fake_page([FEED_ITEMS[0]])

        res = connector.import_catalog_page("BR0089701", 1, with_covers=False)

        self.assertEqual(res["failed"], [], "nenhum livro deveria ter sido recusado")
        self.assertEqual(res["product_ids"], verdadeira.ids)
        self.assertEqual(verdadeira.metabooks_vendor_id, "BR0089701")
        self.assertFalse(sombra.metabooks_vendor_id, "a sombra não deve ser tocada")
        self.assertEqual(
            len(Product.search([("default_code", "=", isbn)])), 2,
            "não pode nascer uma terceira ficha para o mesmo ISBN")

    def test_um_livro_recusado_nao_derruba_a_pagina(self):
        """Um título que o banco recusa cai sozinho; o resto da página entra."""
        # preço que não é número: o ORM recusa a ficha na hora de gravar
        quebrado = {
            "isbn": "9788500000031", "title": "Preço podre",
            "priceBrl": "trinta reais", "publisherMbId": "BR0089701",
        }
        connector = self._fake_page([FEED_ITEMS[0], quebrado, FEED_ITEMS[1]])

        res = connector.import_catalog_page("BR0089701", 1, with_covers=False)

        self.assertEqual(res["imported"], 2)
        self.assertEqual(len(res["failed"]), 1)
        self.assertEqual(res["count"], 3, "a página inteira foi percorrida")
        entraram = self.env["product.template"].browse(res["product_ids"])
        self.assertEqual(set(entraram.mapped("default_code")),
                         {FEED_ITEMS[0]["isbn"], FEED_ITEMS[1]["isbn"]})

    def test_job_conta_os_recusados_e_termina(self):
        """O job soma só o que entrou, guarda os recusados e chega em `done`."""
        job = self.env["metabooks.import.job"].create({"mvb_id": "BR0089701"})
        pagina = {
            "total_pages": 1, "total_elements": 3, "count": 3, "imported": 2,
            "failed": [{"isbn": "9788500000031", "error": "barcode já usado"}],
            "product_ids": [],
        }
        connector = self.env["metabooks.connector"]
        patcher = patch.object(
            type(connector), "import_catalog_page", return_value=pagina)
        patcher.start()
        self.addCleanup(patcher.stop)
        # o job commita a cada página; dentro do teste isso é proibido, e o
        # rollback do TransactionCase já garante o isolamento
        sem_commit = patch.object(self.env.cr, "commit", lambda: None)
        sem_commit.start()
        self.addCleanup(sem_commit.stop)

        job._process_batch()

        self.assertEqual(job.state, "done")
        self.assertEqual(job.imported, 2)
        self.assertEqual(job.skipped, 1)
        self.assertIn("9788500000031", job.message)

    def test_job_devolvido_ao_cron_volta_a_ficar_na_fila(self):
        """No fim do lote o job volta para `queued`, e o cron o reabre na hora.

        Ficando `running`, o cron só o pegaria depois de dez minutos de
        silêncio — o catálogo andaria uma página a cada dez minutos.
        """
        job = self.env["metabooks.import.job"].create({"mvb_id": "BR0089701"})
        pagina = {
            "total_pages": 9, "total_elements": 90, "count": 10, "imported": 10,
            "failed": [], "product_ids": [],
        }
        connector = self.env["metabooks.connector"]
        patcher = patch.object(
            type(connector), "import_catalog_page", return_value=pagina)
        patcher.start()
        self.addCleanup(patcher.stop)
        sem_commit = patch.object(self.env.cr, "commit", lambda: None)
        sem_commit.start()
        self.addCleanup(sem_commit.stop)
        # prazo estourado já na primeira página
        prazo = patch.object(job_mod, "BATCH_DEADLINE_SECONDS", -1)
        prazo.start()
        self.addCleanup(prazo.stop)

        job._process_batch()

        self.assertEqual(job.state, "queued")
        self.assertEqual(job.next_page, 2, "retoma da página seguinte")
        self.assertEqual(job.imported, 10)
        pendentes = self.env["metabooks.import.job"].search([
            ("state", "=", "queued"), ("id", "=", job.id)])
        self.assertTrue(pendentes, "o cron enxerga o job na fila")

    def test_pagina_vazia_nao_inventa_recusados(self):
        """Editora sem catálogo: zero importado, zero recusado, nada quebrado."""
        fake = MagicMock()
        fake.catalog_page.return_value = None
        connector = self._connector_with_fake(fake)

        res = connector.import_catalog_page("BR0000000", 1)

        self.assertEqual(res["imported"], 0)
        self.assertEqual(res["failed"], [])
        self.assertEqual(res["total_pages"], 0)
