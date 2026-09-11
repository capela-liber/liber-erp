# -*- coding: utf-8 -*-
"""Editorial lê as compras (22/08/2026).

"O editorial deve ler POs, principalmente as que têm livros." Quem decide a
edição precisa ver a tiragem comprada e o que a gráfica cobrou, sem depender
do financeiro abrir a tela.

Leitura e só: o que este teste segura é o par -- a porta abre (o editorial lê
pedido e linha) e a parede fica de pé (não escreve, não cria). Mais o filtro
"Com livros", que separa sem esconder: restringir o editorial às POs com livro
esconderia a compra de gráfica, que é assunto editorial como poucos.
"""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_roles')
class TestEditorialLeCompras(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        company = cls.env.company
        cls.assistente = Users.create({
            'name': 'Editorial Assistente', 'login': 'editorial.po@liber.test',
            'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
            'group_ids': [(4, cls.env.ref(
                'liber_roles.group_editorial_assistente').id)],
        })
        cls.fornecedor = cls.env['res.partner'].create({'name': 'Gráfica Teste'})
        cls.livro = cls.env['product.product'].create({
            'name': 'Livro da Tiragem', 'type': 'consu',
            'metabooks_book_title': 'Livro da Tiragem',
        })
        cls.papel = cls.env['product.product'].create({
            'name': 'Papel offset', 'type': 'consu'})
        cls.po = cls.env['purchase.order'].create({
            'partner_id': cls.fornecedor.id,
            'order_line': [(0, 0, {
                'product_id': cls.livro.id, 'product_qty': 1000,
                'price_unit': 3.50, 'name': cls.livro.name,
                'date_planned': '2026-09-01 00:00:00'})],
        })
        cls.po_sem_livro = cls.env['purchase.order'].create({
            'partner_id': cls.fornecedor.id,
            'order_line': [(0, 0, {
                'product_id': cls.papel.id, 'product_qty': 50,
                'price_unit': 120.0, 'name': cls.papel.name,
                'date_planned': '2026-09-01 00:00:00'})],
        })

    def test_o_editorial_le_o_pedido_de_compra(self):
        self.env.invalidate_all()
        po = self.po.with_user(self.assistente)
        self.assertEqual(po.partner_id, self.fornecedor)
        self.assertEqual(po.order_line.product_id, self.livro,
                         "a linha tem que abrir junto: pedido sem linha não diz nada")

    def test_o_editorial_ABRE_pedido_desde_a_cotacao_da_grafica(self):
        """A premissa mudou em 11/09/2026, e o teste acompanha.

        Em 22/08 o contrato era "lê e só". Depois veio o `liber_print_quote`:
        a ficha técnica do livro viaja no pedido à gráfica, e quem manda livro
        para a gráfica é o editorial -- pedir que o financeiro abrisse o
        pedido para cada cotação é pôr um intermediário no meio de uma
        conversa que não é dele. O papel ganhou `purchase.group_purchase_user`
        naquele dia; este teste deixou de dizer a verdade e é ele que estava
        errado.

        A CARONA FICA DITA, como manda a casa em vez de fingir que não existe:
        esse grupo do Odoo não separa pedido de compra de fatura de fornecedor
        e traz escrita em `account.move` junto. Não há grupo mais estreito no
        núcleo. O app Faturamento segue fechado para o editorial, então o
        caminho de tela até uma nota é o botão dentro do próprio pedido.
        """
        self.env.invalidate_all()

        self.po.with_user(self.assistente).write({'partner_ref': 'x'})
        novo = self.env['purchase.order'].with_user(self.assistente).create({
            'partner_id': self.fornecedor.id})

        self.assertTrue(novo.id, "É ele quem manda livro para a gráfica")
        self.assertFalse(
            self.env['ir.ui.menu'].with_user(self.assistente)._visible_menu_ids()
            & {self.env.ref('account.menu_finance').id},
            "Mas o app Faturamento continua fora da tela dele")

    def test_o_gerente_editorial_herda_a_leitura(self):
        """O gerente implica o assistente: não se declara duas vezes."""
        gerente = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Editorial Gerente', 'login': 'editorial.po.g@liber.test',
                'company_id': self.env.company.id,
                'group_ids': [(4, self.env.ref(
                    'liber_roles.group_editorial_gerente').id)],
            })
        self.env.invalidate_all()
        self.assertEqual(self.po.with_user(gerente).partner_id, self.fornecedor)

    def test_o_filtro_com_livros_separa_e_nao_esconde(self):
        """Com o filtro, só as de livro; sem ele, todas continuam lá."""
        dominio = [('order_line.product_id.product_tmpl_id.'
                    'metabooks_book_title', '!=', False)]
        com_livro = self.env['purchase.order'].search(
            dominio + [('id', 'in', (self.po + self.po_sem_livro).ids)])

        self.assertIn(self.po, com_livro)
        self.assertNotIn(self.po_sem_livro, com_livro)
        self.assertIn(self.po_sem_livro,
                      self.po_sem_livro.with_user(self.assistente),
                      "a compra sem livro continua legível: ela também é editorial")
