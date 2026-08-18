# -*- coding: utf-8 -*-
"""O acerto fatura: a baixa da prateleira É a entrega da venda.

Relato da operação (17/08/2026): "Criar fatura" no S do acerto recusava com
"nothing to invoice". A baixa (ACERTO/) e a venda (S) nasciam como dois
documentos que não se conheciam -- nenhum movimento carregava sale_line_id --
e, com o catálogo real em "quantidades entregues" (~80% dele), o entregue da
venda ficava em zero para sempre. Os testes antigos nunca viram isso porque
seus produtos caem na política padrão, "quantidades pedidas".

O que se pinta aqui, SEMPRE com um produto em 'delivery':
- a baixa conta como entrega da venda (qty_delivered = o que foi acertado);
- a fatura sai, no valor do acerto;
- a única transferência do S segue sendo a baixa -- nada de WH/OUT;
- a nota do acerto não herda carga da baixa (frete/transportadora vazios).
"""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAcertoFatura(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        # 'delivery' é a política do catálogo real, e é a que quebrava: o
        # padrão do Odoo ('order') fatura sem olhar a entrega e esconderia
        # exatamente o defeito que este arquivo pinta.
        cls.product = cls.env['product.product'].create({
            'name': 'Livro que Fatura', 'type': 'consu', 'is_storable': True,
            'invoice_policy': 'delivery', 'list_price': 50.0})

    def _agreement(self):
        partner = self.env['res.partner'].create({
            'name': 'Livraria do Acerto', 'is_company': True})
        agreement = self.env['consignment.agreement'].create({
            'partner_id': partner.id, 'company_id': self.company.id,
            'date_start': fields.Date.today() - timedelta(days=1),
        })
        agreement.action_activate()
        return agreement

    def _place_on_shelf(self, partner, qty):
        self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': self.product.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'inventory_quantity': qty + 10,
        }).action_apply_inventory()
        shipment = self.env['consignment.move'].create({
            'partner_id': partner.id,
            'move_kind': 'shipment',
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': qty,
                'product_uom': self.product.uom_id.id,
            })],
        })
        shipment.action_confirm()
        shipment.action_release()
        shipment.picking_id.move_ids.picked = True
        shipment.picking_id.button_validate()

    def _run_settlement(self, reported):
        agreement = self._agreement()
        self._place_on_shelf(agreement.partner_id, reported + 2)
        settlement = self.env['consignment.settlement'].create({
            'partner_id': agreement.partner_id.id,
            'company_id': self.company.id})
        settlement.action_populate_from_shelf()
        settlement.line_ids.qty_reported = reported
        settlement.line_ids.qty_replenish = 0
        settlement.action_run()
        return settlement

    # ------------------------------------------------------------------

    def test_a_baixa_conta_como_entrega(self):
        settlement = self._run_settlement(reported=2)
        so = settlement.sale_order_id
        so.action_confirm()
        line = so.order_line

        self.assertEqual(
            settlement.delivery_picking_id.move_ids.sale_line_id, line,
            "every move of the baixa must point at its S line")
        self.assertEqual(line.qty_delivered, 2,
                         "what left the shelf is what the sale delivered")
        self.assertEqual(so.invoice_status, 'to invoice',
                         "a settled sale must be invoiceable, not 'nothing "
                         "to invoice' -- the bug the operation reported")

    def test_a_fatura_sai_no_valor_do_acerto(self):
        settlement = self._run_settlement(reported=2)
        so = settlement.sale_order_id
        so.action_confirm()

        invoice = so._create_invoices()

        self.assertEqual(invoice.amount_untaxed, 100.0,
                         "2 copies x 50.00, the acerto's own numbers")
        self.assertEqual(so.invoice_status, 'invoiced')

    def test_sem_entrega_do_armazem(self):
        """O vínculo não pode ressuscitar a entrega que o módulo suprime."""
        settlement = self._run_settlement(reported=1)
        so = settlement.sale_order_id
        so.action_confirm()

        self.assertEqual(
            so.picking_ids, settlement.delivery_picking_id,
            "the S's only transfer is the shelf baixa itself -- confirming "
            "the sale must not spawn a WH/OUT for books already settled")

    def test_a_nota_do_acerto_nao_herda_carga(self):
        """A baixa não é carga: frete e transportadora não vazam para a nota.

        A prateleira herda transportadora do cadastro do cliente (via
        liber_transport); antes do filtro em _liber_pickings_da_nota, a nota
        do acerto saía CIF com transportadora -- um transporte que nunca
        houve. Roda só com o liber_nfe_picking instalado (post_install na
        base cheia); numa base mínima o campo nem existe e não há o que vazar.
        """
        if 'nfe_transportadora_id' not in self.env['account.move']._fields:
            self.skipTest("liber_nfe_picking não instalado")
        settlement = self._run_settlement(reported=1)
        picking = settlement.delivery_picking_id
        carrier = self.env['delivery.carrier'].search([], limit=1)
        if carrier:
            picking.carrier_id = carrier
        so = settlement.sale_order_id
        so.action_confirm()
        invoice = so._create_invoices()

        invoice.action_post()

        self.assertFalse(invoice.nfe_transportadora_id,
                         "the baixa's carrier must not become the note's")
        self.assertFalse(invoice.nfe_modalidade_frete,
                         "no freight declared: the acerto emits as 9, "
                         "'sem ocorrência de transporte'")
        self.assertFalse(invoice._liber_volumes_faltando(),
                         "no box to count: the acerto must neither warn at "
                         "confirm nor be barred at emission for volumes")
        # A porta dos volumes na emissão: com movimentação que é toda baixa
        # de prateleira, ela abre sem pedir caixa nem peso.
        invoice._liber_conferir_volumes()
