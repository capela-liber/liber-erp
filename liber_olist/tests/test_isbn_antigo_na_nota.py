# -*- coding: utf-8 -*-
"""A nota do Olist traz o ISBN antigo; o pedido tem o livro com o novo.

Em 06/09/2026, 119 pedidos de marketplace de agosto estavam presos em "A
faturar" com a nota emitida, autorizada e a fatura POSTADA do outro lado. A
fatura não estava amarrada ao pedido porque a nota vinha com o ISBN antigo do
livro (978-85-87329..., o da Hedra), o leitor de XML criou para ele um
produto-fantasma batizado com o próprio ISBN, e o pedido apontava a ficha de
verdade, que só conhece o ISBN novo. Produto diferente, ISBN diferente: a
regra de casamento, que só olhava os dois, não casava "Rosacea" com
"Rosácea".

Três coisas se provam aqui: o fantasma de ISBN é lixo como o de CFOP (e o
espelho sabe o livro); o nome é a terceira chance, sem acento; e um livro de
verdade cujo código tem 13 dígitos não é tomado por lixo.
"""
from odoo.tests import TransactionCase, tagged

from .test_desconto_e_produto_da_nota import TestDescontoEProdutoDaNota


@tagged("post_install", "-at_install", "olist")
class TestIsbnAntigoNaNota(TestDescontoEProdutoDaNota):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rosacea = cls.env['product.product'].create({
            'name': "Rosácea (Orides Fontela; Ieda Sallum)", 'barcode': "9786551590122",
            'default_code': "9786551590122", 'list_price': 62.80, 'type': 'consu'})
        # O fantasma: nome = código = ISBN antigo, sem barcode.
        cls.fantasma = cls.env['product.product'].create({
            'name': "9788587329360", 'default_code': "9788587329360",
            'list_price': 62.80, 'type': 'consu'})

    def test_fantasma_de_isbn_e_lixo(self):
        self.assertTrue(self.env['olist.order']._e_produto_lixo(self.fantasma))

    def test_livro_de_verdade_com_codigo_de_13_digitos_nao_e_lixo(self):
        """A ficha real também tem 13 dígitos no código; o que a distingue é
        ter nome de livro e código de barras."""
        self.assertFalse(self.env['olist.order']._e_produto_lixo(self.rosacea))
        self.assertFalse(self.env['olist.order']._e_produto_lixo(self.livro))

    def test_o_espelho_troca_o_fantasma_pelo_livro_e_amarra_o_pedido(self):
        """O caso do S63534: a nota traz o fantasma, o espelho sabe o livro."""
        pedido, venda = self._pedido(
            [(self.rosacea, 1)], descricoes=["Rosácea"])
        painel = self._painel()
        self._item(painel, self.fantasma, 1, 62.80, 0.0, nome="Rosacea")
        linha = pedido._linhas_de_fatura(painel.panel_items)[0]
        self.assertEqual(linha['product_id'], self.rosacea.id,
                         "a fatura tem de sair com o livro, não com o ISBN")
        self.assertEqual(linha.get('sale_line_ids'), [(6, 0, venda.order_line.ids)])

    def test_sem_espelho_o_nome_sem_acento_amarra(self):
        """Quando nem o espelho ajuda, o nome da nota ("Rosacea", sem acento)
        casa com o do pedido ("Rosácea") se o preço confirmar."""
        pedido, venda = self._pedido([(self.rosacea, 1)], descricoes=["outro texto"])
        painel = self._painel()
        item = self._item(painel, self.fantasma, 1, 62.80, 0.0, nome="ROSACEA")
        linha_pedido = pedido._linha_do_pedido_para(item, set(), self.fantasma)
        self.assertEqual(linha_pedido, venda.order_line)

    def test_o_nome_nao_amarra_com_preco_diferente(self):
        """Dois títulos iguais com preços diferentes são livros diferentes
        (edição de bolso e capa dura): o nome sozinho não decide."""
        pedido, _venda = self._pedido([(self.rosacea, 1)], descricoes=["outro texto"])
        painel = self._painel()
        item = self._item(painel, self.fantasma, 1, 39.90, 0.0, nome="Rosacea")
        self.assertFalse(pedido._linha_do_pedido_para(item, set(), self.fantasma))

    def test_a_chave_de_nome_ignora_acento(self):
        chave = self.env['olist.order']._so_letras_e_numeros
        self.assertEqual(chave("Rosácea – poemas"), chave("ROSACEA - POEMAS"))
        self.assertEqual(chave("Transposição"), "TRANSPOSICAO")

    def test_candidata_unica_amarra_mesmo_com_o_nome_errado(self):
        """O caso do S63612: "QUASIDEAIS" no Olist, "QUASIDEIAS" na ficha.
        Nome nenhum casa; mas o pedido só tem uma linha com aquele preço."""
        pedido, venda = self._pedido([(self.rosacea, 1)], descricoes=["outro texto"])
        painel = self._painel()
        item = self._item(painel, self.fantasma, 1, 62.80, 0.0, nome="ROSCEA")
        self.assertEqual(pedido._linha_do_pedido_para(item, set(), self.fantasma),
                         venda.order_line)

    def test_duas_candidatas_e_decisao_humana(self):
        """Dois livros ao mesmo preço no pedido e um nome que não casa com
        nenhum: o script não escolhe -- escolher errado é pior que não ligar."""
        outro = self.env['product.product'].create({
            'name': "Helianto (Orides Fontela)", 'barcode': "9786551590108",
            'default_code': "9786551590108", 'list_price': 62.80, 'type': 'consu'})
        pedido, _venda = self._pedido([(self.rosacea, 1), (outro, 1)],
                                      descricoes=["x", "y"])
        painel = self._painel()
        item = self._item(painel, self.fantasma, 1, 62.80, 0.0, nome="ROSCEA")
        self.assertFalse(pedido._linha_do_pedido_para(item, set(), self.fantasma))
