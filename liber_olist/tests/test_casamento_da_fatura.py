# -*- coding: utf-8 -*-
"""Qual linha do PEDIDO cada linha da NOTA está pagando.

O defeito que motivou isto (01/09/2026): pedido que entra pela Olist já com a
nota emitida ficava preso em "A faturar" — 58 no prod. A fatura existe, está
postada e paga; o que faltava era o vínculo `sale_line_ids`, e sem ele
`qty_invoiced` fica zero. O Odoo lê zero faturado como "falta faturar tudo".

O motivo do vínculo não se fazer é o produto-fantasma. A fatura nasce do XML, e
quem resolve o produto do XML é o `liber_nfe_xml`, por `cProd`/`cEAN`. Quando
essa procura falha ele CRIA o produto ali mesmo, e nasce um registro cujo nome
é o próprio ISBN, sem código de barras e sem empresa — 163 no dev, 136 com
gêmeo real do mesmo ISBN. O pedido carrega o livro; a nota carrega o gêmeo.
Casando só por `product_id`, nada casa.

Aqui se prova o casamento em si, sem rede: monta-se o pedido e os itens do
painel à mão e chama-se `_linhas_de_fatura`. É a camada de lógica, e é onde o
defeito morava.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCasamentoDaFatura(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Casamento", 'company_id': cls.env.company.id,
            'token': "TOKEN-C", 'read_only': True})
        cls.cliente = cls.env['res.partner'].create({'name': "Compradora"})

        # O livro de verdade: o que o pedido carrega.
        cls.livro = cls.env['product.product'].create({
            'name': "Teia", 'barcode': "9786551590085",
            'default_code': "9786551590085", 'list_price': 60.0, 'type': 'consu'})
        # O fantasma: mesmo ISBN, nome igual ao ISBN, sem código de barras.
        # É o que o liber_nfe_xml cria quando não acha o de cima.
        cls.fantasma = cls.env['product.product'].create({
            'name': "9786551590085", 'default_code': "9786551590085",
            'list_price': 60.0, 'type': 'consu'})
        cls.outro = cls.env['product.product'].create({
            'name': "Helianto", 'barcode': "9786551590115",
            'default_code': "9786551590115", 'list_price': 70.0, 'type': 'consu'})

    # ------------------------------------------------------------------
    def _pedido(self, linhas):
        """Um olist.order com um S por baixo. `linhas` = [(produto, qtd), ...]"""
        venda = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [(0, 0, {'product_id': p.id, 'product_uom_qty': q})
                           for p, q in linhas],
        })
        return self.env['olist.order'].create({
            'account_id': self.account.id, 'valor': 100.0, 'olist_id': '7001',
            'numero': '7001', 'sale_order_id': venda.id,
        }), venda

    def _painel_com(self, itens):
        """`itens` = [(produto, qtd), ...] — os itens lidos do XML."""
        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "n.xml",
            'partner_id': self.cliente.id, 'danfe_no': '9001',
        })
        for produto, qtd in itens:
            self.env['nfe.xml.items'].create({
                'soc_xml_id': painel.id, 'ks_product_id': produto.id,
                'ks_product_name': produto.display_name, 'ks_product_qty': qtd,
                'ks_price': 60.0, 'ks_product_barcode': produto.barcode or False})
        return painel

    @staticmethod
    def _amarradas(linhas_da_fatura):
        """Os ids de linha de pedido que cada linha da fatura reivindicou."""
        return [sorted(v.get('sale_line_ids', [(6, 0, [])])[0][2])
                for v in linhas_da_fatura]

    # ------------------------------------------------------------------
    # Caminho feliz
    # ------------------------------------------------------------------
    def test_o_produto_igual_amarra_direto(self):
        pedido, venda = self._pedido([(self.livro, 2)])
        painel = self._painel_com([(self.livro, 2)])
        linhas = pedido._linhas_de_fatura(painel.panel_items)
        self.assertEqual(self._amarradas(linhas), [venda.order_line.ids],
                         "produto idêntico tem de amarrar na linha do pedido")

    # ------------------------------------------------------------------
    # O defeito: o gêmeo do mesmo ISBN
    # ------------------------------------------------------------------
    def test_o_fantasma_do_mesmo_isbn_amarra_pelo_isbn(self):
        """O caso dos 58 pedidos presos no prod.

        A nota carrega o fantasma, o pedido carrega o livro. São registros
        diferentes do MESMO livro, e é o ISBN que diz isso.
        """
        pedido, venda = self._pedido([(self.livro, 1)])
        painel = self._painel_com([(self.fantasma, 1)])
        linhas = pedido._linhas_de_fatura(painel.panel_items)
        self.assertEqual(
            self._amarradas(linhas), [venda.order_line.ids],
            "produtos diferentes com o mesmo ISBN são o mesmo livro")
        self.assertEqual(linhas[0]['product_id'], self.fantasma.id,
                         "a linha da nota continua dizendo o que a SEFAZ "
                         "autorizou — quem se amarra é o vínculo, não o produto")

    def test_o_fantasma_deixaria_o_pedido_preso_sem_o_conserto(self):
        """A prova pelo avesso: sem casar por ISBN, `qty_invoiced` fica zero.

        Não se testa a ausência do conserto (isso seria testar código que não
        existe mais); testa-se o EFEITO de amarrar, que é a razão de tudo.
        """
        pedido, venda = self._pedido([(self.livro, 3)])
        painel = self._painel_com([(self.fantasma, 3)])
        fatura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id,
            'invoice_line_ids': [(0, 0, v) for v
                                 in pedido._linhas_de_fatura(painel.panel_items)],
        })
        fatura.action_post()
        venda.order_line.invalidate_recordset(['qty_invoiced'])
        self.assertEqual(venda.order_line.qty_invoiced, 3,
                         "amarrado, o faturado tem de aparecer no pedido")

    # ------------------------------------------------------------------
    # Borda: dois itens do mesmo livro
    # ------------------------------------------------------------------
    def test_dois_itens_do_mesmo_livro_nao_disputam_a_mesma_linha(self):
        """Sem memória, os dois amarravam na primeira linha do pedido.

        O efeito era duplo e igualmente ruim: a primeira linha ficava com o
        dobro do faturado (saldo negativo) e a segunda com zero. As duas
        segurando o pedido em "A faturar".
        """
        pedido, venda = self._pedido([(self.livro, 1), (self.livro, 1)])
        painel = self._painel_com([(self.livro, 1), (self.livro, 1)])
        amarradas = self._amarradas(pedido._linhas_de_fatura(painel.panel_items))
        self.assertEqual(len(amarradas), 2)
        self.assertNotEqual(amarradas[0], amarradas[1],
                            "cada item da nota tem de pegar uma linha própria")
        self.assertEqual(sorted(a[0] for a in amarradas),
                         sorted(venda.order_line.ids))

    # ------------------------------------------------------------------
    # Erro: não há par
    # ------------------------------------------------------------------
    def test_sem_par_a_linha_nasce_solta_e_nao_estoura(self):
        """Livro que não está no pedido não inventa vínculo.

        Amarrar no que estivesse à mão seria pior que não amarrar: o pedido
        passaria a dizer que faturou o que não faturou.
        """
        pedido, _venda = self._pedido([(self.livro, 1)])
        painel = self._painel_com([(self.outro, 1)])
        linhas = pedido._linhas_de_fatura(painel.panel_items)
        self.assertEqual(len(linhas), 1)
        self.assertNotIn('sale_line_ids', linhas[0],
                         "sem par, a linha da nota fica solta de propósito")

    def test_produto_sem_isbn_nenhum_nao_casa_com_outro_sem_isbn(self):
        """Vazio não casa com vazio.

        Dois produtos sem `default_code` e sem `barcode` não são o mesmo livro:
        são dois livros sobre os quais não se sabe nada. Casá-los amarraria a
        nota de um no pedido do outro.
        """
        anonimo_a = self.env['product.product'].create({
            'name': "Sem código A", 'type': 'consu', 'list_price': 10.0})
        anonimo_b = self.env['product.product'].create({
            'name': "Sem código B", 'type': 'consu', 'list_price': 10.0})
        pedido, _venda = self._pedido([(anonimo_a, 1)])
        painel = self._painel_com([(anonimo_b, 1)])
        linhas = pedido._linhas_de_fatura(painel.panel_items)
        self.assertNotIn('sale_line_ids', linhas[0])
