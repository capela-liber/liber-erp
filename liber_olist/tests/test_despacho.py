# -*- coding: utf-8 -*-
"""Importar é registrar TUDO: venda, entrega concluída, fatura, recebimento.

A fila de embalagem no Odoo durou um dia (18/08/2026): a entrega ficava
Pronta esperando o funcionário validar na coleta. O dono experimentou e
mandou voltar (19/08, "seria melhor voltar") — o trabalho físico do pacote é
dirigido pelo painel/PDF do Olist, e validar aqui era burocracia dupla. O
Odoo REGISTRA a operação; quem a dirige é o Olist.

O que sobreviveu daquele dia, porque continuou bom: o "A despachar" (nota
emitida e pedido sem registro completo — importar zera), a caixa
Marketplaces (MP/OUT/) e o push descontando o reservado.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDespachoDaCasa(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Despacho", 'company_id': cls.env.company.id,
            'token': "TOKEN-D", 'read_only': True,
            'stock_reserve': 0,
            'order_stock_cutoff': '2026-01-01'})
        cls.livro = cls.env['product.product'].create({
            'name': "Livro do Despacho", 'barcode': "9782222222229",
            'type': 'consu', 'is_storable': True, 'list_price': 50.0})
        cls.wh = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant'].sudo().create({
            'product_id': cls.livro.id,
            'location_id': cls.wh.lot_stock_id.id,
            'inventory_quantity': 10,
        }).action_apply_inventory()
        cls.cliente = cls.env['res.partner'].create({'name': "Comprador D"})

    def _pedido(self, olist_id, situacao, nota='700'):
        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "%s.xml" % olist_id,
            'olist_nota_id': nota, 'olist_account_id': self.account.id,
            'partner_id': self.cliente.id, 'danfe_no': nota,
            'file_create_date': '2026-08-15'})
        self.env['nfe.xml.items'].create({
            'soc_xml_id': painel.id, 'ks_product_id': self.livro.id,
            'ks_product_name': "Livro", 'ks_product_qty': 2,
            'ks_price': 50.0, 'ks_product_barcode': self.livro.barcode})
        return self.env['olist.order'].create({
            'account_id': self.account.id, 'olist_id': olist_id,
            'numero': olist_id, 'situacao': situacao,
            'data_pedido': '2026-08-15', 'id_nota_fiscal': nota,
            'detalhe_lido_em': '2026-08-18 12:00:00',
            'line_ids': [(0, 0, {'codigo': self.livro.barcode,
                                 'descricao': "Livro", 'quantidade': 2,
                                 'valor_unitario': 50.0,
                                 'product_id': self.livro.id})]})

    def test_importar_registra_tudo_de_uma_vez(self):
        """Caminho central: importar conclui a entrega e baixa a prateleira —
        o registro fiel do que o Olist já deu por encaminhado."""
        antes = self.livro.product_tmpl_id._olist_wh_qty(self.account)
        pedido = self._pedido('D-1', 'Enviado')
        self.assertTrue(pedido.a_despachar,
                        "com nota e sem registro, o filtro grita")
        pedido._import_to_odoo()
        entregas = pedido.sale_order_id.picking_ids
        self.assertTrue(entregas)
        self.assertTrue(all(p.state == 'done' for p in entregas),
                        "importar é registrar: a entrega conclui junto")
        self.assertEqual(
            self.livro.product_tmpl_id._olist_wh_qty(self.account), antes - 2,
            "a prateleira baixa no registro")
        self.assertFalse(pedido.a_despachar,
                         "registrado: o grito cala no mesmo clique")

    def test_entregue_registra_igual(self):
        pedido = self._pedido('D-3', 'Entregue', nota='702')
        pedido._import_to_odoo()
        self.assertTrue(all(p.state == 'done'
                            for p in pedido.sale_order_id.picking_ids))
        self.assertFalse(pedido.a_despachar)

    def test_situacao_nova_no_olist_nao_reabre_nada(self):
        """Caso de borda: o pedido já registrado recebe atualização de
        situação na releitura — nada se move, nada estoura."""
        pedido = self._pedido('D-4', 'Enviado', nota='703')
        pedido._import_to_odoo()
        pedido.write({'situacao': 'Entregue'})
        self.assertTrue(all(p.state == 'done'
                            for p in pedido.sale_order_id.picking_ids))

    def test_sem_nota_nao_ha_o_que_despachar(self):
        pedido = self.env['olist.order'].create({
            'account_id': self.account.id, 'olist_id': 'D-5',
            'numero': 'D-5', 'situacao': 'Em aberto',
            'data_pedido': '2026-08-15', 'id_nota_fiscal': '0'})
        self.assertFalse(pedido.a_despachar)

    def test_anterior_ao_corte_e_historia_nao_fila(self):
        self.account.order_stock_cutoff = '2026-08-16'
        pedido = self._pedido('D-6', 'Enviado', nota='704')
        self.assertFalse(pedido.a_despachar)

    def test_o_push_desconta_o_reservado(self):
        """A subtração do reservado ficou: uma remessa de consignação em
        separação, por exemplo, não pode ser oferecida ao marketplace."""
        template = self.livro.product_tmpl_id
        venda = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [(0, 0, {'product_id': self.livro.id,
                                   'product_uom_qty': 3})]})
        venda.action_confirm()          # reserva 3 sem mover
        self.assertEqual(template._olist_reservado_qty(self.account), 3)
        self.assertEqual(template._olist_stock_qty(self.account),
                         template._olist_wh_qty(self.account) - 3,
                         "o reservado sai da oferta sem sair do armazém")

    def test_a_caixa_marketplaces_nasce_no_primeiro_uso(self):
        """A caixa ficou: registro das saídas de marketplace (MP/OUT/),
        separado do palete — mesmo com a entrega concluindo no registro."""
        pedido = self._pedido('D-8', 'Enviado', nota='706')
        pedido._import_to_odoo()
        entrega = pedido.sale_order_id.picking_ids[:1]
        self.assertEqual(entrega.picking_type_id.name, "Marketplaces")
        self.assertTrue(entrega.name.startswith('MP/OUT/'),
                        "a série é MP/OUT/, não o WH/OUT genérico: %s"
                        % entrega.name)
        self.assertEqual(self.account.marketplace_picking_type_id,
                         entrega.picking_type_id)
        pedido2 = self._pedido('D-9', 'Enviado', nota='707')
        pedido2._import_to_odoo()
        self.assertEqual(
            pedido2.sale_order_id.picking_ids.picking_type_id,
            entrega.picking_type_id)

    def test_a_venda_comum_nao_muda_de_caixa(self):
        venda = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [(0, 0, {'product_id': self.livro.id,
                                   'product_uom_qty': 1})]})
        venda.action_confirm()
        tipos = venda.picking_ids.picking_type_id
        self.assertNotIn("Marketplaces", tipos.mapped('name'))

    def test_o_rastreio_tardio_carimba_sozinho(self):
        """O botão morreu, o gesto ficou: rastreio que chega numa releitura
        DEPOIS da importação vai direto para a entrega."""
        pedido = self._pedido('D-10', 'Enviado', nota='708')
        pedido._import_to_odoo()
        entrega = pedido.sale_order_id.picking_ids[:1]
        if 'carrier_tracking_ref' not in entrega._fields:
            self.skipTest("stock_delivery não está instalado")
        self.assertFalse(entrega.carrier_tracking_ref)
        pedido.write({'codigo_rastreamento': 'BR999888777SP'})
        self.assertEqual(entrega.carrier_tracking_ref, 'BR999888777SP')
