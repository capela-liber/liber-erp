# -*- coding: utf-8 -*-
"""O Relatório separa bruto, desconto e líquido (23/08/2026).

A medida antiga era só quantidade × unitário — o BRUTO. O comercial bate meta
pelo que de fato faturou, e o desconto do Olist (cupom, brinde, promoção) some
nessa conta. O Olist dá o desconto no PEDIDO e não diz de qual livro ele saiu:
o rateio pelo peso de cada linha mantém o total exato por dia, canal e mês —
livro a livro é a melhor aproximação que o dado permite, e o campo diz isso.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestValoresDoRelatorio(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Relatório", 'company_id': cls.env.company.id,
            'token': "TOKEN-R", 'read_only': True})

    def _pedido(self, olist_id, desconto, itens):
        return self.env['olist.order'].create({
            'account_id': self.account.id, 'olist_id': olist_id,
            'numero': olist_id, 'situacao': "Aprovado",
            'data_pedido': '2026-08-19', 'valor_desconto': desconto,
            'line_ids': [(0, 0, {'codigo': c, 'descricao': c,
                                 'quantidade': q, 'valor_unitario': v})
                         for c, q, v in itens]})

    def test_the_discount_is_split_by_what_each_line_weighs(self):
        # O pedido 1032 do prod, com os números dele: 367,60 de mercadoria,
        # 49,00 de desconto (uma ecobag de brinde).
        pedido = self._pedido('R1', 49.0, [
            ('9788595820650', 1, 49.0),      # a ecobag
            ('9788595820651', 1, 318.60),    # o resto do carrinho
        ])
        ecobag, resto = pedido.line_ids
        self.assertAlmostEqual(ecobag.valor_total, 49.0, 2)
        self.assertAlmostEqual(resto.valor_total, 318.60, 2)
        # 49 rateado: 49/367,60 para a ecobag, o complemento para o resto.
        self.assertAlmostEqual(ecobag.valor_desconto, 49 * 49 / 367.60, 2)
        self.assertAlmostEqual(
            sum(pedido.line_ids.mapped('valor_desconto')), 49.0, 2)
        # O que importa para a meta: o líquido soma o que o pedido faturou.
        self.assertAlmostEqual(
            sum(pedido.line_ids.mapped('valor_liquido')), 367.60 - 49.0, 2)

    def test_without_discount_gross_and_net_agree(self):
        pedido = self._pedido('R2', 0.0, [('9788595820652', 2, 40.0)])
        linha = pedido.line_ids
        self.assertAlmostEqual(linha.valor_total, 80.0, 2)
        self.assertAlmostEqual(linha.valor_desconto, 0.0, 2)
        self.assertAlmostEqual(linha.valor_liquido, 80.0, 2)

    def test_a_free_order_does_not_divide_by_zero(self):
        # Brinde integral: mercadoria a zero e desconto declarado. Sem bruto
        # não há proporção — o rateio se cala em vez de estourar no import.
        pedido = self._pedido('R3', 10.0, [('9788595820653', 1, 0.0)])
        linha = pedido.line_ids
        self.assertEqual(linha.valor_total, 0.0)
        self.assertEqual(linha.valor_desconto, 0.0)
        self.assertEqual(linha.valor_liquido, 0.0)

    def test_the_discount_follows_a_line_that_changes(self):
        # O espelho REFLETE: reler o detalhe reescreve as linhas, e o rateio
        # tem de acompanhar — o depends cobre as irmãs, não só a própria.
        pedido = self._pedido('R4', 30.0, [('9788595820654', 1, 100.0)])
        pedido.write({'line_ids': [(0, 0, {
            'codigo': '9788595820655', 'descricao': "segundo",
            'quantidade': 1, 'valor_unitario': 200.0})]})
        primeira, segunda = pedido.line_ids
        self.assertAlmostEqual(primeira.valor_desconto, 10.0, 2)
        self.assertAlmostEqual(segunda.valor_desconto, 20.0, 2)

    def test_the_report_groups_by_date_not_by_day(self):
        """O padrão do Odoo: agrupa-se pela DATA, e o dia é um intervalo dela."""
        busca = self.env.ref('liber_olist.view_olist_order_line_search')
        self.assertIn("Data do pedido", busca.arch)
        self.assertNotIn('>Dia<', busca.arch)
        self.assertIn("'group_by': 'order_data'", busca.arch)
