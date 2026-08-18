# -*- coding: utf-8 -*-
"""Qual número sobe para o Olist — e quanto dele fica de reserva.

O primeiro desenho mandava `qty_available` ("Em mãos"), e estava errado: em mãos
soma tudo que é interno da empresa, inclusive o que já saiu da prateleira. O que
se pode vender num marketplace é o **estoque do armazém** — o número que a ficha
do produto mostra em "Estoque", ao lado de "Consignado".

Em cima dele vem a margem de segurança, por conta: a contagem erra, e vender o
último exemplar de um número talvez errado é o que vira pedido cancelado.

Companies e armazéns são REUSADOS do banco (res.company.create tropeça em
fiscalyear_last_day com o `account` instalado). Ver NOTES.md §10.6.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_olist.models import olist_client

OK_RESP = ('{"retorno":{"status":"OK","registros":[{"registro":'
           '{"id":9,"saldoEstoque":"7.0000","registroCriado":false}}]}}')


@tagged('post_install', '-at_install')
class TestOlistStockQuantity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})

        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.company = cls.warehouse.company_id
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Qty", 'company_id': cls.company.id,
            'token': "TOKEN-Q", 'read_only': False,
        })

        cls.book = cls.env['product.template'].create({
            'name': "Livro do Armazém",
            'barcode': "9788888888880",
            'olist_produto_id': "900",
            'type': 'consu',
            'is_storable': True,
        })

        # 10 na prateleira do armazém...
        cls.NA_PRATELEIRA = 10.0
        Quant = cls.env['stock.quant'].sudo()
        Quant._update_available_quantity(
            cls.book.product_variant_id, cls.warehouse.lot_stock_id,
            cls.NA_PRATELEIRA)

        # ...e 4 numa localização interna FORA da área de estoque. "Em mãos"
        # conta esses 4; a prateleira, não. É essa a diferença que a tela do
        # usuário mostrava como 65 contra 61.
        cls.FORA = 4.0
        cls.fora_loc = cls.env['stock.location'].create({
            'name': "Fora da prateleira",
            'usage': 'internal',
            'location_id': cls.warehouse.view_location_id.id,
            'company_id': cls.company.id,
        })
        Quant._update_available_quantity(
            cls.book.product_variant_id, cls.fora_loc, cls.FORA)

    def _capture(self):
        sent = []

        def fake_update(token, id_produto, qty, **kw):
            sent.append(qty)
            return ('{}', OK_RESP)

        return sent, patch.object(olist_client, 'update_estoque',
                                  side_effect=fake_update)

    # -- o número ------------------------------------------------------------
    def test_on_hand_really_is_bigger(self):
        # Guarda do próprio cenário: se "Em mãos" não fosse maior, os testes
        # abaixo passariam sem provar nada.
        self.assertEqual(
            self.book.with_context(
                allowed_company_ids=[self.company.id]).qty_available,
            self.NA_PRATELEIRA + self.FORA)

    def test_sends_warehouse_stock_not_on_hand(self):
        sent, patcher = self._capture()
        with patcher:
            self.book._push_stock_to_olist(self.account)
        self.assertEqual(sent, [self.NA_PRATELEIRA],
                         "subiu 'Em mãos' em vez do estoque do armazém")

    def test_reading_on_hand_first_does_not_poison_the_number(self):
        """A armadilha do cache do core, fixada aqui.

        `product.template._compute_quantities` declara depends_context só com
        'warehouse_id' — sem 'location'. Então, num template, ler "Em mãos"
        antes deixa esse valor cacheado sob uma chave que ignora a
        localização, e a leitura seguinte com `location=` devolveria 14 em vez
        de 10. O número que sobe para o Olist não pode depender de quem leu o
        quê antes nesta transação.
        """
        poison = self.book.with_context(
            allowed_company_ids=[self.company.id]).qty_available
        self.assertEqual(poison, self.NA_PRATELEIRA + self.FORA)
        self.assertEqual(self.book._olist_wh_qty(self.account),
                         self.NA_PRATELEIRA)

    def test_matches_the_number_on_the_product_screen(self):
        # A garantia que o usuário pediu: o que está na tela é o que sobe.
        # `soc_qty_wh` é o campo por trás do botão "Estoque" da ficha.
        Template = self.env['product.template']
        if 'soc_qty_wh' not in Template._fields:
            self.skipTest("liber_soc_moves não está instalado")
        na_tela = self.book.with_context(
            allowed_company_ids=[self.company.id]).soc_qty_wh
        self.assertEqual(self.book._olist_wh_qty(self.account), na_tela)

    def test_no_warehouse_sends_zero_not_everything(self):
        sem_wh = self.env['res.company'].search(
            [('id', 'not in', self.env['stock.warehouse'].search(
                []).company_id.ids)], limit=1)
        if not sem_wh:
            self.skipTest("todas as empresas do banco têm armazém")
        conta = self.env['olist.account'].create({
            'name': "Sem armazém", 'company_id': sem_wh.id, 'token': "T", 'read_only': False,
        })
        self.assertEqual(self.book._olist_stock_qty(conta), 0.0)

    # -- a margem ------------------------------------------------------------
    def test_margin_is_subtracted(self):
        self.account.stock_reserve = 3
        sent, patcher = self._capture()
        with patcher:
            self.book._push_stock_to_olist(self.account)
        self.assertEqual(sent, [self.NA_PRATELEIRA - 3])

    def test_margin_floors_at_zero_never_negative(self):
        # Estoque abaixo da margem: o livro sai como esgotado. Um número
        # negativo aqui seria aceito pelo Olist e viraria saldo negativo lá.
        self.account.stock_reserve = 25
        sent, patcher = self._capture()
        with patcher:
            self.book._push_stock_to_olist(self.account)
        self.assertEqual(sent, [0.0])

    def test_zero_margin_is_the_default(self):
        self.assertEqual(self.account.stock_reserve, 0)
        sent, patcher = self._capture()
        with patcher:
            self.book._push_stock_to_olist(self.account)
        self.assertEqual(sent, [self.NA_PRATELEIRA])

    def test_margin_is_per_account_not_global(self):
        outra = self.env['stock.warehouse'].search(
            [('company_id', '!=', self.company.id)], limit=1)
        if not outra:
            self.skipTest("banco com uma empresa só tem armazém")
        conta_b = self.env['olist.account'].create({
            'name': "Olist outra", 'company_id': outra.company_id.id,
            'token': "T-B", 'read_only': False, 'stock_reserve': 5,
        })
        self.account.stock_reserve = 1
        self.assertEqual(self.account.stock_reserve, 1)
        self.assertEqual(conta_b.stock_reserve, 5)

    # -- o log confere -------------------------------------------------------
    def test_log_shows_stock_margin_and_sent(self):
        self.account.stock_reserve = 3
        _sent, patcher = self._capture()
        with patcher:
            self.book._push_stock_to_olist(self.account)
        log = self.book.with_context(
            allowed_company_ids=[self.company.id]).olist_stock_log
        self.assertIn("estoque do armazém: 10", log)
        self.assertIn("margem: 3", log)
        self.assertIn("qty sent (tipo=B): 7", log)
        # e "Em mãos" fica no log como referência, para explicar a diferença
        self.assertIn("em mãos (referência): 14", log)
