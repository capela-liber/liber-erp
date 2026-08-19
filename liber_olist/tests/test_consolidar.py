# -*- coding: utf-8 -*-
"""Consolidar o histórico: o passado entra por inteiro, a prateleira não se move.

Decisão do dono (19/08/2026): para efeito de histórico, o pedido anterior ao
corte precisa de S, movimentação, fatura e recebimento — inclusive mexendo no
estoque. O truque que torna isso seguro é a ÂNCORA: o movimento histórico é
datado no dia do pedido, e um ajuste de inventário no fim do lote devolve
cada prateleira tocada ao número de hoje — que já descontava, fisicamente, o
livro que saiu há meses. Verificado antes de construir: zero chaves do
histórico já lançadas no razão — consolidar cria, não duplica.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestConsolidarHistorico(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist História", 'company_id': cls.env.company.id,
            'token': "TOKEN-H", 'read_only': True,
            'order_stock_cutoff': '2026-08-01'})
        cls.livro = cls.env['product.product'].create({
            'name': "Livro da História", 'barcode': "9783333333336",
            'type': 'consu', 'is_storable': True, 'list_price': 40.0})
        cls.wh = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant'].sudo().create({
            'product_id': cls.livro.id,
            'location_id': cls.wh.lot_stock_id.id,
            'inventory_quantity': 8,
        }).action_apply_inventory()
        cls.cliente = cls.env['res.partner'].create({'name': "Comprador H"})

    def _pedido_antigo(self, olist_id, nota, data='2026-02-10'):
        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "%s.xml" % olist_id,
            'olist_nota_id': nota, 'olist_account_id': self.account.id,
            'partner_id': self.cliente.id, 'danfe_no': nota,
            'file_create_date': data})
        self.env['nfe.xml.items'].create({
            'soc_xml_id': painel.id, 'ks_product_id': self.livro.id,
            'ks_product_name': "Livro", 'ks_product_qty': 2,
            'ks_price': 40.0, 'ks_product_barcode': self.livro.barcode})
        return self.env['olist.order'].create({
            'account_id': self.account.id, 'olist_id': olist_id,
            'numero': olist_id, 'situacao': 'Entregue',
            'data_pedido': data, 'id_nota_fiscal': nota,
            'detalhe_lido_em': '2026-08-19 12:00:00',
            'line_ids': [(0, 0, {'codigo': self.livro.barcode,
                                 'descricao': "Livro", 'quantidade': 2,
                                 'valor_unitario': 40.0,
                                 'product_id': self.livro.id})]})

    def test_o_passado_entra_por_inteiro_e_a_prateleira_nao_se_move(self):
        """Caminho feliz: S, entrega concluída DATADA no passado, fatura
        datada na emissão — e o estoque de hoje termina onde estava."""
        template = self.livro.product_tmpl_id
        antes = template._olist_wh_qty(self.account)
        pedido = self._pedido_antigo('H-1', '801801')
        self.assertEqual(pedido.state, 'anterior_corte')

        pedido.action_consolidar_historico()

        self.assertTrue(pedido.sale_order_id)
        entrega = pedido.sale_order_id.picking_ids[:1]
        self.assertEqual(entrega.state, 'done')
        self.assertEqual(str(entrega.date_done)[:10], '2026-02-10',
                         "o movimento histórico é datado no dia do pedido")
        self.assertTrue(all(str(m.date)[:10] == '2026-02-10'
                            for m in entrega.move_ids))
        self.assertTrue(pedido.invoice_id)
        self.assertEqual(str(pedido.invoice_id.invoice_date), '2026-02-10',
                         "a fatura é datada na emissão da nota")
        self.assertEqual(pedido.invoice_id.state, 'posted')
        self.assertEqual(
            template._olist_wh_qty(self.account), antes,
            "a âncora devolve a prateleira ao número de hoje")

    def test_dentro_do_corte_recusa(self):
        """Caso de erro: dentro do corte o caminho é o Importar comum — a
        consolidação não pode virar porta lateral do presente."""
        pedido = self._pedido_antigo('H-2', '801802', data='2026-08-15')
        self.assertNotEqual(pedido.state, 'anterior_corte')
        with self.assertRaises(UserError):
            pedido._consolidar_um({})

    def test_livro_nao_casado_barra_o_pedido(self):
        pedido = self._pedido_antigo('H-3', '801803')
        pedido.line_ids.write({'product_id': False})
        with self.assertRaises(UserError):
            pedido._consolidar_um({})

    def test_a_adocao_apresenta_o_painel_orfao_ao_pedido(self):
        """O XML que veio pelo legado não sabe de que nota é: a releitura o
        adota (carimba id e conta) e o pedido passa a achá-lo."""
        from unittest.mock import patch
        from odoo.addons.liber_olist.models import olist_client
        orfao = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "orfao.xml",
            'partner_id': self.cliente.id, 'danfe_no': '901901',
            'key': '35260211111111000111550010009019011000000019',
            'file_create_date': '2026-02-05'})
        self.assertFalse(orfao.olist_account_id)
        with patch.object(olist_client, 'list_notas', return_value=iter([
                {'id': '901901', 'chave_acesso': orfao.key,
                 'situacao': '7'}])):
            resultado = self.account._sync_notas()
        self.assertEqual(resultado['adopted'], 1)
        self.assertEqual(orfao.olist_nota_id, '901901')
        self.assertEqual(orfao.olist_account_id, self.account)

    def test_completa_o_registro_que_ficou_pela_metade(self):
        """O caso 927 (19/08/2026): importado como registro (S em rascunho),
        confirmado à mão pelo dono esperando a nota — "confirmei e nada". A
        consolidação assume dali: conclui com data histórica, fatura e âncora.
        """
        pedido = self._pedido_antigo('H-4', '801804')
        pedido._import_to_odoo()             # fora do corte: só registro
        venda = pedido.sale_order_id
        self.assertTrue(venda)
        self.assertFalse(pedido.invoice_id)
        venda.action_confirm()               # o clique à mão
        self.assertTrue(venda.picking_ids)
        template = self.livro.product_tmpl_id
        antes = template._olist_wh_qty(self.account)

        pedido.action_consolidar_historico()

        self.assertTrue(pedido.invoice_id)
        self.assertTrue(all(p.state == 'done' for p in venda.picking_ids))
        self.assertEqual(str(venda.picking_ids[0].date_done)[:10],
                         '2026-02-10', "a conclusão leva a data histórica")
        self.assertEqual(template._olist_wh_qty(self.account), antes,
                         "a âncora vale também para o completamento")
        with self.assertRaises(UserError):
            pedido._consolidar_um({})        # de novo: já consolidado
