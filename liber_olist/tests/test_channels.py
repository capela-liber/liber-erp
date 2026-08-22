# -*- coding: utf-8 -*-
"""O espelho de canais: o nome de lá, o canal de venda daqui (18/08/2026).

O Olist manda o nome do canal DELE ("Mercado Livre", "Online: Hedra") e a casa
tem os seus ("Marketplaces", "Online", "Livrarias independentes"). Até esta
data a integração casava por nome e, falhando, CRIAVA um `crm.team` com o nome
que tivesse chegado — foi assim que nasceu o canal 98 "Hedra" da EdLab Press no
staging, único ativo da empresa enquanto os canais legítimos estavam
arquivados.

O que se prova aqui:

1. ler o detalhe REGISTRA o canal no espelho e não cria canal de venda nenhum;
2. canal mapeado carimba o pedido de venda e a fatura;
3. canal não mapeado deixa o pedido entrar sem canal, sem exceção;
4. o mesmo canal visto duas vezes não duplica a linha do espelho.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_olist.models import olist_client

LISTAGEM = [
    {'id': '5001', 'numero': '5001', 'data_pedido': '10/08/2026',
     'nome': 'Comprador', 'situacao': 'Entregue', 'valor': 49.0},
    {'id': '5002', 'numero': '5002', 'data_pedido': '11/08/2026',
     'nome': 'Outro comprador', 'situacao': 'Entregue', 'valor': 49.0},
]

DETALHE = {
    'id': '5001', 'numero': '5001', 'situacao': 'Entregue',
    'id_nota_fiscal': '0',
    'ecommerce': {'nomeEcommerce': 'Online: Hedra',
                  'numeroPedidoEcommerce': '77'},
    'intermediador': {'nome': 'Shopify'},
    'cliente': {'nome': 'Comprador', 'cpf_cnpj': '171.037.078-55'},
    'itens': [{'item': {'id_produto': '9001', 'codigo': '978-85-7715-835-5',
                        'descricao': 'A toca iluminada', 'quantidade': '1',
                        'valor_unitario': '49.00'}}],
}


@tagged('post_install', '-at_install')
class TestOlistChannels(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Canais", 'company_id': cls.env.company.id,
            'token': "TOKEN-C", 'read_only': True})
        cls.livro = cls.env['product.product'].create({
            'name': "A toca iluminada", 'barcode': "9788577158355",
            'list_price': 49.0, 'type': 'consu', 'is_storable': True})

    # -- ferramentas --------------------------------------------------------
    def _pull(self):
        with patch.object(olist_client, 'list_pedidos',
                          return_value=iter(LISTAGEM)):
            return self.account._pull_orders(interactive=False)

    def _detalhe(self, pedido, dados=None):
        with patch.object(olist_client, 'get_pedido',
                          return_value=dados or DETALHE):
            pedido._read_detail()

    def _pedido(self, numero='5001'):
        return self.env['olist.order'].search(
            [('account_id', '=', self.account.id), ('numero', '=', numero)])

    def _espelho(self, nome='Online: Hedra'):
        return self.env['olist.channel'].search(
            [('account_id', '=', self.account.id), ('name', '=', nome)])

    def _arquiva_xml(self, pedido, nota='4321'):
        """A importação exige XML arquivado (§17): a fatura nasce da nota."""
        if pedido.id_nota_fiscal in (False, '0'):
            pedido.id_nota_fiscal = nota
        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "n-%s.xml" % nota,
            'olist_nota_id': pedido.id_nota_fiscal,
            'olist_account_id': self.account.id,
            'danfe_no': nota,
            'partner_id': self.env['res.partner'].search([], limit=1).id})
        self.env['nfe.xml.items'].create({
            'soc_xml_id': painel.id, 'ks_product_id': self.livro.id,
            'ks_product_name': "A toca iluminada", 'ks_product_qty': 1,
            'ks_price': 49.0, 'ks_product_barcode': '9788577158355'})
        pedido.invalidate_recordset()
        pedido.modified(['id_nota_fiscal'])
        return painel

    # -- (a) a descoberta ---------------------------------------------------
    def test_reading_the_detail_registers_the_channel_and_creates_no_team(self):
        """Ler descobre o canal — e só isso.

        Registrar o nome que chegou é barato e não decide nada. Criar um canal
        de venda a partir dele é decidir a taxonomia comercial da casa a partir
        de uma leitura de API, que é o que aconteceu no staging.
        """
        antes = self.env['crm.team'].with_context(
            active_test=False).search_count([])
        self._pull()
        self._detalhe(self._pedido())

        espelho = self._espelho()
        self.assertTrue(espelho, "o canal não foi registrado no espelho")
        self.assertEqual(espelho.name, "Online: Hedra",
                         "o nome tem de ser o de lá, cru")
        self.assertEqual(espelho.platform, "Shopify")
        self.assertFalse(espelho.team_id, "o mapeamento nasce vazio")
        self.assertEqual(self.env['crm.team'].with_context(
            active_test=False).search_count([]), antes,
            "a leitura criou canal de venda")

    def test_an_existing_team_of_the_same_name_is_prefilled(self):
        """Conveniência, não regra: nome idêntico já vem apontado."""
        equipe = self.env['crm.team'].create({
            'name': "Online: Hedra", 'company_id': self.account.company_id.id})
        self._pull()
        self._detalhe(self._pedido())
        self.assertEqual(self._espelho().team_id, equipe)

    # -- (b) o canal mapeado carimba ----------------------------------------
    def test_a_mapped_channel_stamps_the_sale_order_and_the_invoice(self):
        equipe = self.env['crm.team'].create({
            'name': "Marketplaces", 'company_id': self.account.company_id.id})
        self._pull()
        pedido = self._pedido()
        self._detalhe(pedido)
        self._espelho().team_id = equipe

        pedido.invalidate_recordset()
        self.assertEqual(pedido.team_id, equipe,
                         "mapear depois tem de alcançar o pedido já lido")
        self._arquiva_xml(pedido)
        pedido._import_to_odoo()
        self.assertEqual(pedido.sale_order_id.team_id, equipe)
        self.assertEqual(pedido.invoice_id.team_id, equipe,
                         "a fatura entrou sem canal")

    def test_mapping_does_not_overwrite_a_channel_set_by_hand(self):
        """Canal escolhido a dedo num pedido é decisão, e não se reescreve."""
        a_dedo = self.env['crm.team'].create({
            'name': "Escolhido a dedo",
            'company_id': self.account.company_id.id})
        equipe = self.env['crm.team'].create({
            'name': "Marketplaces", 'company_id': self.account.company_id.id})
        self._pull()
        pedido = self._pedido()
        self._detalhe(pedido)
        pedido.team_id = a_dedo
        self._espelho().team_id = equipe
        pedido.invalidate_recordset()
        self.assertEqual(pedido.team_id, a_dedo)

    # -- (c) o canal não mapeado não trava nada -----------------------------
    def test_an_unmapped_channel_lets_the_order_in_without_a_channel(self):
        """Vazio é resposta legítima: "ainda não classificado"."""
        self._pull()
        pedido = self._pedido()
        self._detalhe(pedido)
        self._arquiva_xml(pedido)

        pedido._import_to_odoo()          # nenhuma exceção

        self.assertTrue(pedido.sale_order_id, "o pedido não entrou")
        self.assertFalse(pedido.sale_order_id.team_id)
        self.assertEqual(pedido.canal, "Online: Hedra",
                         "o dado cru do Olist continua guardado")
        self.assertFalse(self.env['crm.team'].with_context(
            active_test=False).search_count([('name', '=ilike', "Online: Hedra")]))

    def test_resolve_team_never_creates_a_team(self):
        antes = self.env['crm.team'].with_context(
            active_test=False).search_count([])
        self.assertFalse(self.account._resolve_team("Canal que não existe"))
        self.assertEqual(self.env['crm.team'].with_context(
            active_test=False).search_count([]), antes)
        self.assertTrue(self._espelho("Canal que não existe"),
                        "resolver devia ao menos ter registrado o canal")

    def test_the_account_counts_what_is_still_unmapped(self):
        self._pull()
        self._detalhe(self._pedido())
        self.account.invalidate_recordset()
        self.assertEqual(self.account.channel_count, 1)
        self.assertEqual(self.account.channel_unmapped_count, 1)

    # -- (d) o mesmo canal duas vezes ---------------------------------------
    def test_the_same_channel_seen_twice_is_one_line(self):
        self._pull()
        self._detalhe(self._pedido('5001'))
        self._detalhe(self._pedido('5002'),
                      dict(DETALHE, id='5002', numero='5002'))
        self.assertEqual(self.env['olist.channel'].search_count(
            [('account_id', '=', self.account.id),
             ('name', '=', "Online: Hedra")]), 1,
            "o mesmo canal virou duas linhas do espelho")

    def test_rereading_the_same_order_does_not_duplicate_the_line(self):
        self._pull()
        pedido = self._pedido()
        self._detalhe(pedido)
        self._detalhe(pedido)
        self.assertEqual(len(self._espelho()), 1)

    def test_the_mapping_button_registers_what_the_orders_said(self):
        """O botão da conta descobre em lote e leva à tela do mapa."""
        self._pull()
        # Canal gravado sem passar pela descoberta (é o estado de um banco
        # que já lia pedidos antes de 18/08/2026).
        self._pedido('5001').write({'canal': "Online: Circuito"})
        acao = self.account.action_map_channels()
        self.assertEqual(acao['res_model'], 'olist.channel')
        self.assertTrue(self._espelho("Online: Circuito"))
        self.assertFalse(self.env['crm.team'].with_context(
            active_test=False).search_count([('name', '=ilike', "Online: Circuito")]))

    def test_the_line_counts_the_orders_of_its_channel(self):
        self._pull()
        self._detalhe(self._pedido('5001'))
        self._detalhe(self._pedido('5002'),
                      dict(DETALHE, id='5002', numero='5002'))
        espelho = self._espelho()
        espelho.invalidate_recordset()
        self.assertEqual(espelho.order_count, 2)
