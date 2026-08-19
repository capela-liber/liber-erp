# -*- coding: utf-8 -*-
"""A ficha sincronizada sai na política de faturamento da casa.

Até 18/08/2026 isso acontecia por acidente. `invoice_policy` é campo computado
e armazenado no Odoo 19, com `@api.depends('type')`, e o compute força `order`
em toda mercadoria; como o conector manda `"type": "consu"` em todo upsert, o
sincronismo devolvia o livro ao padrão certo sem que nada neste módulo dissesse
isso -- e apagando, de lado, qualquer escolha manual.

O valor é o mesmo; o que muda é ser DECISÃO em vez de efeito colateral. Estes
testes cobram isso: que o conector leia o interruptor da casa (Vendas >
Faturamento > Política de faturamento, semeado pelo `edlab_stack`) e o grave
por escrito.

Por que importa: uma mercadoria em `delivery` fica com `qty_delivered` = 0 para
sempre -- o acerto da consignação vende sem entrega física -- e nunca fatura.
"""
from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged

ISBN = "9788599296299"

ONIX = {
    "identifiers": [{"productIdentifierType": "03", "idValue": ISBN}],
    "titles": [{"title": "Livro da Política"}],
    "prices": [{"priceType": "02", "priceAmount": 40.0}],
    "publisherData": {"name": "Editora Teste", "shortName": "ET", "mvbId": "BR0089701"},
    "form": {"productForm": "BC"},
}


@tagged("post_install", "-at_install")
class TestPoliticaDeFaturamento(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Default = self.env["ir.default"]
        fake = MagicMock()
        fake.get_product_by_isbn.return_value = ONIX
        self.connector = self.env["metabooks.connector"]
        patcher = patch.object(
            type(self.connector), "_get_client", return_value=fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _definir_padrao(self, valor):
        """Mexe no interruptor da casa como a tela de Definições mexeria."""
        self.Default.set("product.template", "invoice_policy", valor)
        # `_get_model_defaults` é ormcached: sem isto o conector leria o valor
        # velho dentro do mesmo teste.
        self.env.registry.clear_cache()
        self.addCleanup(self.env.registry.clear_cache)

    # ------------------------------------------------------------------ #
    #  Caminho feliz                                                      #
    # ------------------------------------------------------------------ #
    def test_livro_importado_sai_na_politica_da_casa(self):
        """O padrão da casa é `order`: fatura-se o que foi pedido."""
        self._definir_padrao("order")

        produto = self.connector.import_isbns([ISBN])["products"]

        self.assertEqual(produto.invoice_policy, "order")

    def test_o_conector_le_o_interruptor_e_nao_o_compute_do_core(self):
        """A prova de que a decisão é nossa.

        Com o padrão em `delivery`, o compute do core ainda quereria `order`
        (o livro é `type='consu'`). Se a ficha sair em `delivery`, é porque o
        conector gravou o valor por escrito -- e não porque o core decidiu.
        """
        self._definir_padrao("delivery")

        produto = self.connector.import_isbns([ISBN])["products"]

        self.assertEqual(produto.invoice_policy, "delivery")

    # ------------------------------------------------------------------ #
    #  Borda                                                              #
    # ------------------------------------------------------------------ #
    def test_base_sem_o_padrao_preenchido_cai_em_order(self):
        """O chão. Todas as bases da casa estavam assim até 18/08/2026:
        o interruptor vazio, e nada segurando o valor."""
        self.Default.discard_values("product.template", "invoice_policy", ["order", "delivery"])
        self.env.registry.clear_cache()
        self.addCleanup(self.env.registry.clear_cache)
        self.assertFalse(
            self.Default._get("product.template", "invoice_policy"),
            "o teste precisa começar com o interruptor vazio")

        produto = self.connector.import_isbns([ISBN])["products"]

        self.assertEqual(produto.invoice_policy, "order")

    def test_ficha_existente_volta_ao_padrao_na_proxima_sincronizacao(self):
        """Comportamento documentado, não surpresa: a escolha manual não
        sobrevive ao sincronismo. Era o que já acontecia de lado -- agora
        acontece por escrito, e o chatter registra (o campo é `tracking`)."""
        self._definir_padrao("order")
        livro = self.env["product.template"].create({
            "name": "Livro da Política", "default_code": ISBN, "barcode": ISBN,
            "type": "consu", "invoice_policy": "delivery"})
        self.assertEqual(livro.invoice_policy, "delivery")

        self.connector.import_isbns([ISBN])

        self.assertEqual(livro.invoice_policy, "order")

    # ------------------------------------------------------------------ #
    #  O helper sozinho                                                   #
    # ------------------------------------------------------------------ #
    def test_house_invoice_policy_nunca_devolve_vazio(self):
        """Quem chama grava o resultado num campo obrigatório: um `False`
        aqui viraria uma ficha sem política."""
        self.Default.discard_values("product.template", "invoice_policy", ["order", "delivery"])
        self.env.registry.clear_cache()
        self.addCleanup(self.env.registry.clear_cache)

        self.assertEqual(self.connector._house_invoice_policy(), "order")
