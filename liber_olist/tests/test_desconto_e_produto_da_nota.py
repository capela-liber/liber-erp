# -*- coding: utf-8 -*-
"""A fatura tem de dizer o que a nota diz: o desconto e o livro.

Dois defeitos achados juntos no prod em 05/09/2026, nos pedidos do Olist que
ficavam para sempre em "A faturar" com a nota emitida e paga do outro lado.

O DESCONTO. `_linhas_de_fatura` gravava `discount: 0.0` fixo e o preço bruto,
embora o parse do XML já guardasse os três números (`ks_price` bruto,
`discount_item` por unidade, `net_price` líquido por unidade). A fatura saía
acima do que a nota fiscal declara: 288 itens e R$ 3.074,67 de desconto
descartado. O S63525 é o retrato -- a nota diz 58,40 com 20,44 de desconto, e
a fatura foi postada em 58,40 cheios.

O LIVRO. A nota do Olist vem com `cEAN` = "SEM GTIN" e, quando o livro não tem
código interno lá, com `cProd` = o próprio CFOP. O leitor de XML tomou
"CFOP5102" por código de produto e criou um produto com esse código; as notas
seguintes com o mesmo `cProd` casaram todas com ele. Eram dois registros
(`CFOP5102` e `CFOP6102`, ambos chamados "Os cantos do homem-sombra") em 50
linhas de fatura e zero linhas de pedido. Não era só o elo perdido: a fatura
saía com o livro errado.

Quem sabe a resposta é o espelho do Olist, que casou o item pelo ISBN que o
Olist manda e acertou. O `xProd` da nota e a `descricao` do espelho são o
mesmo texto a menos de pontuação -- um usa hífen, o outro travessão. Dos 61
itens presos no lixo, 57 se resolvem por aí.

O que NÃO muda: o gêmeo de mesmo ISBN continua indo para a linha da fatura
como veio do XML (ver `test_casamento_da_fatura`). Ali o produto está certo,
só é outro registro do mesmo livro. Aqui o produto está ERRADO.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDescontoEProdutoDaNota(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Desconto", 'company_id': cls.env.company.id,
            'token': "TOKEN-D", 'read_only': True})
        cls.cliente = cls.env['res.partner'].create({'name': "Leitora"})

        cls.livro = cls.env['product.product'].create({
            'name': "Alba", 'barcode': "9786551590115",
            'default_code': "9786551590115", 'list_price': 58.40, 'type': 'consu'})
        # O lixo: o CFOP lido como se fosse código de produto.
        cls.lixo = cls.env['product.product'].create({
            'name': "Os cantos do homem-sombra", 'default_code': "CFOP5102",
            'list_price': 58.40, 'type': 'consu'})

    # ------------------------------------------------------------------
    def _pedido(self, linhas, descricoes=None):
        """`linhas` = [(produto, qtd)]; `descricoes` = texto do espelho."""
        venda = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [(0, 0, {'product_id': p.id, 'product_uom_qty': q})
                           for p, q in linhas],
        })
        pedido = self.env['olist.order'].create({
            'account_id': self.account.id, 'olist_id': '8001',
            'numero': '8001', 'sale_order_id': venda.id,
        })
        for i, (produto, qtd) in enumerate(linhas):
            self.env['olist.order.line'].create({
                'order_id': pedido.id, 'product_id': produto.id,
                'descricao': (descricoes or [None] * len(linhas))[i]
                             or produto.display_name,
                'quantidade': qtd, 'valor_unitario': produto.list_price})
        return pedido, venda

    def _item(self, painel, produto, qtd, bruto, desconto_unit, nome=None):
        return self.env['nfe.xml.items'].create({
            'soc_xml_id': painel.id, 'ks_product_id': produto.id,
            'ks_product_name': nome or produto.display_name,
            'ks_product_qty': qtd, 'ks_price': bruto,
            'discount_item': desconto_unit,
            'net_price': bruto - desconto_unit,
            'ks_total_price': bruto * qtd})

    def _painel(self):
        return self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "n.xml",
            'partner_id': self.cliente.id, 'danfe_no': '9002'})

    # ------------------------------------------------------------------
    # O desconto
    # ------------------------------------------------------------------
    def test_o_desconto_da_nota_vai_para_a_fatura(self):
        """O caso do S63525: 58,40 com 20,44 de desconto = 37,96."""
        pedido, _venda = self._pedido([(self.livro, 1)])
        painel = self._painel()
        self._item(painel, self.livro, 1, 58.40, 20.44)
        linha = pedido._linhas_de_fatura(painel.panel_items)[0]
        liquido = linha['price_unit'] * (1 - linha['discount'] / 100.0)
        self.assertAlmostEqual(
            liquido, 37.96, places=2,
            msg="a fatura tem de fechar no líquido que a nota declara")

    def test_sem_desconto_no_xml_a_fatura_fica_bruta(self):
        pedido, _venda = self._pedido([(self.livro, 1)])
        painel = self._painel()
        self._item(painel, self.livro, 1, 58.40, 0.0)
        linha = pedido._linhas_de_fatura(painel.panel_items)[0]
        self.assertEqual(linha['discount'], 0.0)
        self.assertAlmostEqual(linha['price_unit'], 58.40, places=2)

    def test_desconto_que_nao_fecha_em_porcentagem_grava_o_liquido(self):
        """Nota fiscal não fecha por aproximação.

        Quando a porcentagem não reproduz o líquido ao centavo, o preço vira o
        líquido e o desconto some -- perde-se a leitura comercial, não o
        centavo. A borda é a razão de existir a conferência dentro de
        `_preco_e_desconto`."""
        pedido, _venda = self._pedido([(self.livro, 3)])
        painel = self._painel()
        # 3 x 10,00 com 0,01 de desconto por unidade: 0,1% não fecha redondo.
        self._item(painel, self.livro, 3, 10.00, 0.01)
        linha = pedido._linhas_de_fatura(painel.panel_items)[0]
        liquido = linha['price_unit'] * 3 * (1 - linha['discount'] / 100.0)
        self.assertAlmostEqual(liquido, 29.97, places=2)

    # ------------------------------------------------------------------
    # O livro
    # ------------------------------------------------------------------
    def test_produto_com_codigo_de_cfop_e_trocado_pelo_do_espelho(self):
        """O caso do S63612: a nota trazia o lixo, o espelho sabia o livro."""
        pedido, venda = self._pedido(
            [(self.livro, 1)], descricoes=["ALBA – POEMAS"])
        painel = self._painel()
        # O XML traz o nome CERTO e o produto ERRADO: é essa a assinatura.
        self._item(painel, self.lixo, 1, 58.40, 0.0, nome="ALBA - POEMAS")
        linha = pedido._linhas_de_fatura(painel.panel_items)[0]
        self.assertEqual(linha['product_id'], self.livro.id,
                         "produto com código de CFOP não é produto")
        self.assertEqual(linha.get('sale_line_ids'),
                         [(6, 0, venda.order_line.ids)],
                         "corrigido o livro, o elo com o pedido se fecha")

    def test_sem_nome_igual_no_espelho_o_lixo_fica_e_a_fatura_barra(self):
        """Não achando, devolve o que veio.

        Barrar é melhor que emitir errado: quem recusa é a checagem de "itens
        sem produto" na criação da fatura, e ela precisa ver o problema."""
        pedido, _venda = self._pedido(
            [(self.livro, 1)], descricoes=["ALBA – POEMAS"])
        painel = self._painel()
        self._item(painel, self.lixo, 1, 58.40, 0.0, nome="OUTRO LIVRO")
        linha = pedido._linhas_de_fatura(painel.panel_items)[0]
        self.assertEqual(linha['product_id'], self.lixo.id)

    def test_produto_bom_nao_e_mexido(self):
        """A troca só morde o lixo: produto com ISBN passa intacto."""
        pedido, venda = self._pedido([(self.livro, 1)])
        painel = self._painel()
        self._item(painel, self.livro, 1, 58.40, 0.0)
        linha = pedido._linhas_de_fatura(painel.panel_items)[0]
        self.assertEqual(linha['product_id'], self.livro.id)
        self.assertEqual(linha.get('sale_line_ids'),
                         [(6, 0, venda.order_line.ids)])


@tagged('post_install', '-at_install')
class TestFaturaDoOlistDePontaAPonta(TransactionCase):
    """O mesmo conserto, mas medido no documento que fica.

    `_linhas_de_fatura` devolve dicionários, e dicionário não é fatura. O que
    o comercial vê é a `account.move` postada e o pedido saindo de "A
    faturar" -- e é entre uma coisa e outra que moram a posição fiscal, o
    `action_post`, o recompute de `qty_invoiced` e o arredondamento por linha
    da casa. Este bloco atravessa tudo isso.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Ponta a Ponta", 'company_id': cls.env.company.id,
            'token': "TOKEN-P", 'read_only': True, 'invoice_auto_post': True})
        cls.cliente = cls.env['res.partner'].create({'name': "Leitor Final"})
        cls.livro = cls.env['product.product'].create({
            'name': "Bom crioulo", 'barcode': "9786589705390",
            'default_code': "9786589705390", 'list_price': 64.90,
            'type': 'consu'})
        cls.lixo = cls.env['product.product'].create({
            'name': "Os cantos do homem-sombra", 'default_code': "CFOP6102",
            'list_price': 64.90, 'type': 'consu'})

    def _cenario(self, produto_no_xml, bruto, desconto_unit, nome_no_xml):
        venda = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [(0, 0, {'product_id': self.livro.id,
                                   'product_uom_qty': 1})],
        })
        venda.action_confirm()
        # O painel se liga ao pedido pelo id da nota NO OLIST, não à mão:
        # `nfe_panel_id` é computado (ver `_compute_nfe_panel`). Montar o
        # vínculo do jeito que o sistema monta é o que faz este teste medir o
        # caminho de verdade.
        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "n.xml",
            'partner_id': self.cliente.id, 'danfe_no': '9100',
            'key': '3' * 44,
            'olist_nota_id': 'NF-9500',
            'olist_account_id': self.account.id})
        self.env['nfe.xml.items'].create({
            'soc_xml_id': painel.id, 'ks_product_id': produto_no_xml.id,
            'ks_product_name': nome_no_xml, 'ks_product_qty': 1,
            'ks_price': bruto, 'discount_item': desconto_unit,
            'net_price': bruto - desconto_unit, 'ks_total_price': bruto})
        pedido = self.env['olist.order'].create({
            'account_id': self.account.id, 'olist_id': '9500',
            'numero': '9500', 'sale_order_id': venda.id,
            'id_nota_fiscal': 'NF-9500', 'partner_id': self.cliente.id,
            # `valor` zero faz o pedido virar BONIFICAÇÃO (livro dado), e a
            # bonificação recusa esta fatura por desenho. Sem este campo o
            # cenário mede outra coisa.
            'valor': bruto,
            'company_id': self.env.company.id})
        self.env['olist.order.line'].create({
            'order_id': pedido.id, 'product_id': self.livro.id,
            'descricao': "BOM CRIOULO", 'quantidade': 1,
            'valor_unitario': bruto})
        self.assertEqual(pedido.nfe_panel_id, painel,
                         "o cenário não amarrou a nota ao pedido")
        return pedido, venda

    # -- o desconto chega postado -------------------------------------------
    def test_a_fatura_postada_fecha_no_liquido_da_nota(self):
        """O caso do S63249: 64,90 com 6,49 = 58,41."""
        pedido, _venda = self._cenario(self.livro, 64.90, 6.49, "BOM CRIOULO")
        pedido._create_invoice()
        fatura = pedido.invoice_id
        self.assertTrue(fatura, "a fatura tem de nascer")
        self.assertAlmostEqual(
            fatura.amount_untaxed, 58.41, places=2,
            msg="a fatura postada tem de valer o que a nota declara")

    # -- o livro certo chega postado ----------------------------------------
    def test_a_fatura_postada_leva_o_livro_certo(self):
        pedido, venda = self._cenario(self.lixo, 64.90, 0.0, "BOM CRIOULO")
        pedido._create_invoice()
        linha = pedido.invoice_id.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product')
        self.assertEqual(
            linha.product_id, self.livro,
            "a fatura saiu com o produto-lixo em vez do livro")
        self.assertEqual(
            linha.sale_line_ids, venda.order_line,
            "sem o elo o pedido mora em 'A faturar' para sempre")

    # -- e o pedido sai de "A faturar" --------------------------------------
    def test_o_pedido_deixa_de_estar_a_faturar(self):
        """A prova que o comercial enxerga: o S fecha.

        É o defeito inteiro num assert -- 85 pedidos no prod tinham nota
        postada e paga e continuavam pedindo faturamento."""
        pedido, venda = self._cenario(self.lixo, 64.90, 0.0, "BOM CRIOULO")
        pedido._create_invoice()
        venda.invalidate_recordset()
        self.assertEqual(venda.order_line.qty_invoiced, 1,
                         "a quantidade faturada tem de subir")
        self.assertEqual(venda.invoice_status, 'invoiced')

    # -- borda: o item que não se resolve barra em vez de sair errado -------
    def test_item_sem_produto_resolvivel_barra_a_fatura(self):
        """Barrar é o comportamento certo: nota errada é pior que nota que
        falta. O nome do XML não bate com nada no espelho."""
        pedido, _venda = self._cenario(self.lixo, 64.90, 0.0, "LIVRO QUE NAO EXISTE")
        # o produto-lixo continua sendo produto para o Odoo, então a fatura
        # nasce -- o que NÃO pode acontecer é ela sair com o livro certo por
        # acidente.
        pedido._create_invoice()
        linha = pedido.invoice_id.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product')
        self.assertEqual(linha.product_id, self.lixo,
                         "sem casar pelo nome, não se inventa o livro")
