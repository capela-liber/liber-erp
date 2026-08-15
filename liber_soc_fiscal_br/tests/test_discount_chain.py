# -*- coding: utf-8 -*-
"""O desconto de ponta a ponta: do contrato até a INV.

O desconto da casa é um NÚMERO, não um preço menor. Quem o dilui no preço
unitário apaga a única coisa que o resto do sistema precisa ler depois:

- o royalty especial (`liber_copyright_contracts_analytics`) só reconhece a
  venda com desconto qualificado por `invoice_line_ids.discount`;
- o `valor_desconto` da NFe (`liber_nfe_focus`) sai da diferença entre o bruto
  (quantidade x preço) e o subtotal -- sem desconto no campo, o DANFE sai sem
  desconto nenhum;
- e o próprio acerto, cujo mapa imprime a coluna "Desc.%".

Um preço unitário já líquido faz as três coisas mentirem em silêncio: os
números continuam batendo no total, e o desconto some do razão.

Este teste segue o desconto pelos dois caminhos que a casa tem, elo por elo:

    contrato ──> linha do acerto ──> Pedido S ──> INV        (o que vendeu)
             └─> reposição C000 ──> nota REM/                (o que repõe)
"""
from odoo import fields
from odoo.tests import TransactionCase, tagged

LIST_PRICE = 100.0
DESCONTO = 40.0  # o do contrato
NA_PRATELEIRA = 10
VENDIDO = 4
REPOR = 3


@tagged("post_install", "-at_install", "soc_discount")
class TestDiscountChain(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1)
        cls.product = cls.env["product.product"].create({
            "name": "Livro do Desconto",
            "type": "consu",
            "is_storable": True,
            "list_price": LIST_PRICE,
        })
        # Lista de preços PRÓPRIA, sem regra: o preço bruto é o de tabela, e o
        # único desconto em jogo é o do contrato. Sem isto o teste herdaria a
        # lista do demo ("Benelux", -10%) e mediria o demo, não o módulo.
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Tabela cheia (fixture desconto)",
            "company_id": cls.company.id,
        })
        cls.partner = cls.env["res.partner"].create({
            "name": "Livraria do Desconto", "is_company": True})
        cls.partner.with_company(cls.company).property_product_pricelist = cls.pricelist
        cls.agreement = cls.env["consignment.agreement"].create({
            "partner_id": cls.partner.id,
            "company_id": cls.company.id,
            "date_start": fields.Date.today(),
            "discount": DESCONTO,
        })
        cls.agreement.action_activate()

    # -- cenário ------------------------------------------------------------
    def _estoque(self, qty):
        self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": self.product.id,
            "location_id": self.warehouse.lot_stock_id.id,
            "inventory_quantity": qty,
        }).action_apply_inventory()

    def _na_prateleira(self, qty):
        """Coloca na prateleira do cliente pelo motor, não escrevendo quant:
        o acerto tem que acertar contra uma prateleira que chegou lá como as
        de verdade chegam."""
        remessa = self.env["consignment.move"].create({
            "partner_id": self.partner.id,
            "move_kind": "shipment",
            "line_ids": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": qty,
                "product_uom": self.product.uom_id.id,
            })],
        })
        remessa.action_confirm()
        remessa.action_release()
        remessa.picking_id.move_ids.picked = True
        remessa.picking_id.button_validate()

    def _acerto(self, vendido=VENDIDO, repor=REPOR, desconto_na_linha=None):
        acerto = self.env["consignment.settlement"].create({
            "partner_id": self.partner.id, "company_id": self.company.id})
        acerto.action_populate_from_shelf()
        linha = acerto.line_ids
        linha.qty_reported = vendido
        linha.qty_replenish = repor
        if desconto_na_linha is not None:
            linha.discount = desconto_na_linha
        return acerto

    def _wire_fiscal(self):
        """A posição fiscal da remessa de consignação (o par auto-quitado)."""
        espelho = self.env["account.account"].search(
            [("code", "=", "CONTSD")], limit=1) or \
            self.env["account.account"].create({
                "code": "CONTSD",
                "name": "(-) Remessa de Consignação (fixture desconto)",
                "account_type": "income_other",
                "company_ids": [(4, self.company.id)]})
        fpos = self.env["account.fiscal.position"].search(
            [("name", "=", "Consignação — Desconto (fixture)"),
             ("company_id", "=", self.company.id)], limit=1) or \
            self.env["account.fiscal.position"].create({
                "name": "Consignação — Desconto (fixture)",
                "company_id": self.company.id,
                "auto_invoice_paid": True,
                "auto_invoice_paid_account_id": espelho.id})
        self.company.consignment_shipment_fiscal_position_id = fpos
        return fpos

    def _faturar(self, pedido):
        pedido.action_confirm()
        pedido.order_line.qty_delivered = pedido.order_line.product_uom_qty
        return pedido._create_invoices()

    def _bruto_menos_liquido(self, linha):
        """O desconto como o `liber_nfe_focus` o lê para a NFe."""
        return round(
            (linha.quantity if linha._name == "account.move.line"
             else linha.product_uom_qty) * linha.price_unit
            - linha.price_subtotal, 2)

    # -- elo 1: contrato -> linha do acerto ---------------------------------
    def test_o_contrato_manda_o_desconto_para_a_linha_do_acerto(self):
        self._estoque(50)
        self._na_prateleira(NA_PRATELEIRA)
        linha = self._acerto().line_ids

        self.assertEqual(linha.discount, DESCONTO,
                         "a linha do acerto não herdou o desconto do contrato")
        self.assertEqual(linha.price_unit, LIST_PRICE,
                         "o preço da linha tem que ser o BRUTO -- desconto "
                         "diluído no preço some do razão")
        self.assertAlmostEqual(
            linha.price_subtotal, VENDIDO * LIST_PRICE * 0.6, places=2,
            msg="o subtotal do acerto tem que aplicar o desconto uma vez")

    # -- elo 2: acerto -> Pedido S ------------------------------------------
    def test_o_acerto_leva_o_desconto_para_o_pedido_S(self):
        self._estoque(50)
        self._na_prateleira(NA_PRATELEIRA)
        acerto = self._acerto()
        acerto.action_run()

        pedido = acerto.sale_order_id
        self.assertTrue(pedido, "o acerto não gerou o Pedido S")
        linha = pedido.order_line
        self.assertEqual(linha.discount, DESCONTO,
                         "o desconto não atravessou o acerto até o Pedido S")
        self.assertEqual(linha.price_unit, LIST_PRICE)
        self.assertAlmostEqual(
            linha.price_subtotal, VENDIDO * LIST_PRICE * 0.6, places=2)

    # -- elo 3: Pedido S -> INV (o que o usuário vê) ------------------------
    def test_o_desconto_chega_na_fatura(self):
        """O elo que a casa cobrou: a INV tem que levar o desconto em conta.

        E "em conta" é no CAMPO: preço bruto e Desc.% preenchido. A INV que
        mostra o preço já líquido e Desc. 0 fecha o mesmo total e mente para
        todo mundo que lê depois.
        """
        self._estoque(50)
        self._na_prateleira(NA_PRATELEIRA)
        acerto = self._acerto()
        acerto.action_run()
        fatura = self._faturar(acerto.sale_order_id)

        self.assertTrue(fatura, "o Pedido S não gerou fatura")
        linha = fatura.invoice_line_ids.filtered(
            lambda l: l.product_id == self.product)
        self.assertEqual(len(linha), 1)
        self.assertEqual(linha.discount, DESCONTO,
                         "a INV saiu sem o desconto no campo próprio")
        self.assertEqual(linha.price_unit, LIST_PRICE,
                         "a INV saiu com o preço já líquido: o desconto "
                         "sumiu do razão")
        self.assertAlmostEqual(
            linha.price_subtotal, VENDIDO * LIST_PRICE * 0.6, places=2)
        # o que a NFe vai declarar em vDesc
        self.assertAlmostEqual(
            self._bruto_menos_liquido(linha), VENDIDO * LIST_PRICE * 0.4,
            places=2, msg="a NFe sairia com vDesc zerado")

    # -- caso de borda: o desconto digitado na linha manda ------------------
    def test_o_desconto_da_linha_vence_o_do_contrato(self):
        """O contrato é o padrão, não a lei: quem acerta pode mudar a linha,
        e é o número da LINHA que tem que chegar na fatura."""
        self._estoque(50)
        self._na_prateleira(NA_PRATELEIRA)
        acerto = self._acerto(desconto_na_linha=25.0)
        acerto.action_run()
        fatura = self._faturar(acerto.sale_order_id)

        self.assertEqual(acerto.sale_order_id.order_line.discount, 25.0)
        linha = fatura.invoice_line_ids.filtered(
            lambda l: l.product_id == self.product)
        self.assertEqual(linha.discount, 25.0,
                         "a fatura reescreveu o desconto que o operador digitou")
        self.assertAlmostEqual(
            linha.price_subtotal, VENDIDO * LIST_PRICE * 0.75, places=2)

    # -- elo 4: acerto -> reposição C000 ------------------------------------
    def test_a_reposicao_C000_nasce_com_o_desconto(self):
        """A reposição é do MESMO contrato que o acerto que a pediu.

        Sem o desconto, o C000 nasce pelo preço de tabela e a nota de remessa
        declara um valor que a casa nunca cobraria -- e é esse valor que sai
        no DANFE de consignação.
        """
        self._estoque(50)
        self._na_prateleira(NA_PRATELEIRA)
        acerto = self._acerto()
        acerto.action_run()

        reposicao = acerto.replenishment_order_id
        self.assertTrue(reposicao, "o acerto não gerou a reposição C")
        self.assertTrue(reposicao.is_consignment)
        linha = reposicao.order_line
        self.assertEqual(linha.price_unit, LIST_PRICE,
                         "o C000 de reposição saiu com preço fora do contrato")
        self.assertEqual(linha.discount, DESCONTO,
                         "o C000 de reposição nasceu sem o desconto do contrato")

    # -- elo 5: Pedido C -> nota REM/ ---------------------------------------
    def test_a_nota_de_remessa_leva_o_desconto_do_pedido_C(self):
        self._estoque(50)
        self._wire_fiscal()
        pedido = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "is_consignment": True,
            "consignment_type": "opening",
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": 6,
                "price_unit": LIST_PRICE,
                "discount": DESCONTO})],
        })
        pedido.action_confirm()
        pedido.action_generate_remessa_note()

        linha = pedido.remessa_note_move_id.invoice_line_ids.filtered(
            lambda l: l.product_id == self.product)
        self.assertEqual(linha.discount, DESCONTO,
                         "a nota REM/ saiu sem o desconto do Pedido C")
        self.assertEqual(linha.price_unit, LIST_PRICE)
        self.assertAlmostEqual(
            self._bruto_menos_liquido(linha), 6 * LIST_PRICE * 0.4, places=2)

    # -- caso de erro: nunca descontar duas vezes ---------------------------
    def test_lista_de_precos_do_contrato_nao_desconta_duas_vezes(self):
        """Contrato com lista de preços E desconto: o desconto entra UMA vez.

        `_compute_price_unit` lê a lista com `_get_product_price`, que já
        devolve o preço LÍQUIDO. Se o desconto do contrato também for aplicado
        sobre ele, o cliente é descontado duas vezes -- e ninguém percebe,
        porque os dois números são plausíveis.
        """
        lista = self.env["product.pricelist"].create({
            "name": "30% (fixture desconto)",
            "company_id": self.company.id,
            "item_ids": [(0, 0, {
                "applied_on": "3_global",
                "compute_price": "percentage",
                "percent_price": 30.0})],
        })
        self.agreement.pricelist_id = lista
        self._estoque(50)
        self._na_prateleira(NA_PRATELEIRA)
        linha = self._acerto().line_ids

        liquido = linha.price_unit * (1 - linha.discount / 100.0)
        self.assertGreaterEqual(
            liquido, LIST_PRICE * (1 - DESCONTO / 100.0) - 0.01,
            "desconto duplo: a lista já devolveu o preço líquido (%.2f) e o "
            "desconto do contrato (%.0f%%) foi aplicado de novo, fechando em "
            "%.2f" % (linha.price_unit, linha.discount, liquido))
