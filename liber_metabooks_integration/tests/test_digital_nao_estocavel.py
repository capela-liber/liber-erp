# -*- coding: utf-8 -*-
"""Ebook e abook são serviço, e nunca estocáveis, venha a escrita de onde vier.

A regra morava só no conector, e em 27/09/2026 havia 112 fichas que a
Metabooks chama de ebook/abook marcadas como estocáveis: a migração do 15, o
`08_consignment` e o import da NFe ligam `is_storable` por conta própria. E não
basta desligar o estoque: mercadoria (`consu`) abre entrega ao confirmar o
pedido, e o extrato da Bookwire vira pedido de venda. A trava agora é do
produto; estes testes cobram cada caminho.
"""
from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged

ISBN_EBOOK = "9788599296305"


@tagged("post_install", "-at_install")
class TestDigitalEServico(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        BookType = cls.env["metabooks.book.type"]

        def tipo(nome):
            return (BookType.search([("name", "=", nome)], limit=1)
                    or BookType.create({"name": nome}))

        cls.ebook = tipo("ebook")
        cls.abook = tipo("abook")
        cls.pbook = tipo("pbook")
        cls.Product = cls.env["product.template"]

    def _livro(self, tipo, **vals):
        return self.Product.create(dict({
            "name": "Livro %s" % tipo.name,
            "type": "consu",
            "is_storable": True,
            "metabooks_product_type": tipo.id,
        }, **vals))

    def assertServico(self, produto):
        self.assertEqual(produto.type, "service")
        self.assertFalse(produto.is_storable)
        self.assertEqual(produto.invoice_policy, "order")

    # ------------------------------------------------------------------ #
    #  Caminho feliz                                                      #
    # ------------------------------------------------------------------ #
    def test_ebook_nasce_servico_mesmo_pedindo_mercadoria_estocavel(self):
        self.assertServico(self._livro(self.ebook))

    def test_abook_nasce_servico(self):
        self.assertServico(self._livro(self.abook))

    def test_ligar_o_estoque_de_um_ebook_nao_pega(self):
        """É o que o `08_consignment` e o import da NFe fazem."""
        ebook = self._livro(self.ebook)
        ebook.write({"type": "consu", "is_storable": True})
        self.assertServico(ebook)
        ebook.write({"is_storable": True})
        self.assertServico(ebook)
        ebook.write({"invoice_policy": "delivery"})
        self.assertServico(ebook)

    def test_livro_que_vira_ebook_vira_servico(self):
        """Ficha criada pela NFe como estocável; a Metabooks diz que é ebook."""
        livro = self.Product.create({
            "name": "Ficha da NFe", "type": "consu", "is_storable": True})
        self.assertTrue(livro.is_storable)
        livro.write({"metabooks_product_type": self.ebook.id})
        self.assertServico(livro)

    def test_sincronizar_ebook_existente_vira_servico(self):
        """O caminho do conector: a ficha existia, estocável, pelo ISBN."""
        existente = self.Product.create({
            "name": "Ebook da migração", "type": "consu", "is_storable": True,
            "default_code": ISBN_EBOOK, "barcode": ISBN_EBOOK})
        fake = MagicMock()
        fake.get_product_by_isbn.return_value = {
            "identifiers": [{"productIdentifierType": "15", "idValue": ISBN_EBOOK}],
            "titles": [{"title": "Ebook da migração"}],
            "productType": "ebook",
            "publisherData": {"name": "Editora Teste", "shortName": "ET"},
        }
        connector = self.env["metabooks.connector"]
        with patch.object(type(connector), "_get_client", return_value=fake):
            produto = connector.import_isbns([ISBN_EBOOK])["products"]
        self.assertEqual(produto, existente)
        self.assertServico(existente)
        self.assertEqual(existente.invoice_policy, "order")

    def test_pedido_de_ebook_nao_abre_entrega(self):
        """O motivo de ser serviço: o extrato da Bookwire vira pedido.

        Com o interruptor da casa em `delivery`, como estava no `dev`: o ebook
        fatura o pedido mesmo assim.
        """
        self.env["ir.default"].set("product.template", "invoice_policy", "delivery")
        self.env.registry.clear_cache()
        self.addCleanup(self.env.registry.clear_cache)
        if "picking_ids" not in self.env["sale.order"]._fields:
            self.skipTest("sale_stock não instalado")
        ebook = self._livro(self.ebook, list_price=10.0)
        cliente = self.env["res.partner"].create({"name": "Bookwire Teste"})
        pedido = self.env["sale.order"].create({
            "partner_id": cliente.id,
            "order_line": [(0, 0, {
                "product_id": ebook.product_variant_id.id,
                "product_uom_qty": 3, "price_unit": 10.0})],
        })
        pedido.action_confirm()
        self.assertFalse(pedido.picking_ids)
        self.assertEqual(pedido.order_line.qty_to_invoice, 3)

    # ------------------------------------------------------------------ #
    #  Borda                                                              #
    # ------------------------------------------------------------------ #
    def test_livro_impresso_continua_mercadoria_estocavel(self):
        pbook = self._livro(self.pbook)
        pbook.write({"is_storable": True, "name": "Outro nome"})
        self.assertEqual(pbook.type, "consu")
        self.assertTrue(pbook.is_storable)

    def test_conector_manda_impresso_como_mercadoria(self):
        Connector = type(self.env["metabooks.connector"])
        self.assertEqual(Connector._product_type("pbook"), "consu")
        self.assertEqual(Connector._product_type(None), "consu")
        self.assertEqual(Connector._product_type(" Ebook "), "service")
        self.assertEqual(Connector._product_type("abook"), "service")

    def test_produto_sem_tipo_metabooks_nao_e_assunto_da_regra(self):
        avulso = self.Product.create({
            "name": "Caneca", "type": "consu", "is_storable": True})
        self.assertEqual(avulso.type, "consu")
        self.assertTrue(avulso.is_storable)

    # ------------------------------------------------------------------ #
    #  Lote misto: corrige, não recusa                                    #
    # ------------------------------------------------------------------ #
    def test_lote_misto_nao_cai_e_so_o_digital_muda(self):
        """Quem liga o estoque em lote não pode cair por um ebook no meio."""
        lote = self._livro(self.pbook) | self._livro(self.ebook) \
            | self._livro(self.abook)
        lote.write({"type": "consu", "is_storable": True})
        self.assertEqual(lote.mapped("type"), ["consu", "service", "service"])
        self.assertEqual(lote.mapped("is_storable"), [True, False, False])
