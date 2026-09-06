# -*- coding: utf-8 -*-
"""O cartão da estante mostra o livro, não o código de barras.

Pedido da direção em 10/08/2026: "pode tirar o ISBN daqui; na busca já
localizamos, ninguém sabe de cor para filtrar lendo".

O ponto destes testes não é o que saiu — é o que NÃO saiu junto. A linha do
ISBN vem do kanban do core (`product`), compartilhado com Vendas ▸ Produtos e
Inventário ▸ Produtos. Herdar direto teria tirado o código de todo mundo, e
ninguém notaria até o dia em que alguém do depósito procurasse por ele.
"""
import re

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestKanbanLivros(TransactionCase):

    def _arch(self, xmlid, user=None):
        """A view COMO ELA CHEGA a um usuário.

        Com `user`, é isto que se mede: o Odoo apaga da view o elemento cujo
        `groups` o usuário não tem, e admin tem todos os grupos -- medir com
        admin não prova nada sobre o que a equipe enxerga.
        """
        view = self.env.ref(xmlid)
        modelo = self.env['product.template']
        if user is not None:
            modelo = modelo.with_user(user)
        return modelo.get_view(view_id=view.id, view_type='kanban')['arch']

    @staticmethod
    def _campos(arch):
        """Os nomes de campo que o cartão realmente carrega."""
        return re.findall(r'<field[^>]*\bname="([a-z_0-9]+)"', arch)

    @classmethod
    def _com_inventario(cls):
        """Alguém do perfil que TEM o app Inventário."""
        return cls.env['res.users'].create({
            'name': 'Com Inventário',
            'login': 'com_inventario',
            'password': 'com_inventario',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('stock.group_stock_user').id])],
        })

    @classmethod
    def _sem_inventario(cls):
        """Um usuário do perfil da casa: interno, e fora do app Inventário.

        É o Comercial: o liber_roles retira dele o `stock.group_stock_user` de
        propósito (31/07/2026), para que o app Inventário não apareça.
        """
        return cls.env['res.users'].create({
            'name': 'Comercial sem Inventário',
            'login': 'sem_inventario',
            'password': 'sem_inventario',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    def test_o_isbn_sai_do_cartao_da_estante(self):
        arch = self._arch('liber_metabooks_integration.view_metabooks_books_kanban')
        self.assertNotIn(
            'default_code', arch,
            'o ISBN voltou ao cartão de Livros')
        # o cartão sem o resto não seria um cartão
        self.assertIn('list_price', arch, 'o preço sumiu do cartão')
        self.assertIn('name="name"', arch, 'o título sumiu do cartão')

    def test_a_estante_so_tira_o_isbn_do_cartao_do_core(self):
        """A varredura contra sumiço: nada MAIS pode faltar no cartão.

        A variante de Livros existe para tirar uma coisa só. Qualquer outra
        diferença em relação ao cartão do core é perda silenciosa -- foi assim
        que a quantidade em estoque virou assunto, e nenhum teste reclamou
        porque nenhum comparava os dois.

        Comparar campo a campo, e não procurar por nomes escolhidos a dedo, é
        o que faz este teste continuar valendo quando o Odoo mudar o cartão.
        """
        usuario = self._sem_inventario()
        core = set(self._campos(self._arch(
            'product.product_template_kanban_view', user=usuario)))
        livros = set(self._campos(self._arch(
            'liber_metabooks_integration.view_metabooks_books_kanban',
            user=usuario)))
        self.assertEqual(
            core - livros, {'default_code'},
            'o cartão de Livros perdeu algo além do ISBN')
        self.assertFalse(
            livros - core,
            'o cartão de Livros ganhou campo que o do core não tem')

    def test_quem_e_do_inventario_ve_a_quantidade_nos_dois(self):
        """O caminho feliz do perfil que tem o grupo.

        A linha "On hand" é do módulo `stock` e vem com
        `groups="stock.group_stock_user"`; o Odoo a apaga da view de quem não
        tem o grupo. A variante de Livros não mexe nisso, de propósito: quem
        enxerga em Vendas enxerga aqui, e quem não enxerga lá não enxerga aqui.
        """
        usuario = self._com_inventario()
        for xmlid in ('product.product_template_kanban_view',
                      'liber_metabooks_integration.view_metabooks_books_kanban'):
            self.assertIn('qty_available', self._arch(xmlid, user=usuario),
                          'a quantidade sumiu de %s' % xmlid)

    def test_a_quantidade_sai_sem_casa_decimal(self):
        """Livro não se vende em fração: "65", não "65,00"."""
        arch = self._arch(
            'liber_metabooks_integration.view_metabooks_books_kanban',
            user=self._com_inventario())
        pos = arch.index('name="qty_available"')
        self.assertIn(
            'digits="[16, 0]"', arch[pos - 150:pos + 150],
            'a quantidade do cartão voltou a sair com casa decimal')

    def test_a_casa_decimal_e_so_nossa(self):
        """Borda: o cartão do core não pode ter sido mexido junto."""
        arch = self._arch('product.product_template_kanban_view',
                          user=self._com_inventario())
        pos = arch.index('name="qty_available"')
        self.assertNotIn(
            'digits="[16, 0]"', arch[pos - 150:pos + 150],
            'a mudança da estante vazou para o cartão de produto do core')

    def test_o_kanban_padrao_de_produto_fica_como_estava(self):
        """A metade que importa: a mudança é DAQUI, não do Odoo inteiro.

        Se um dia alguém trocar o `mode="primary"` da variante por uma herança
        comum "para simplificar", este teste é quem avisa que Vendas e
        Inventário perderam o código do produto junto.
        """
        arch = self._arch('product.product_template_kanban_view')
        self.assertIn(
            'default_code', arch,
            'o kanban padrão de produto perdeu o código: a variante da estante '
            'vazou para Vendas e Inventário')

    def test_a_estante_aponta_para_a_variante(self):
        """Sem esta ligação a variante existe e não é usada por ninguém."""
        acao = self.env.ref('liber_metabooks_integration.action_metabooks_books')
        variante = self.env.ref(
            'liber_metabooks_integration.view_metabooks_books_kanban')
        kanban = acao.view_ids.filtered(lambda v: v.view_mode == 'kanban')
        self.assertEqual(kanban.view_id, variante,
                         'a ação Livros não usa a variante do kanban')
        # lista e formulário seguem os padrão, de propósito
        for modo in ('list', 'form'):
            outra = acao.view_ids.filtered(lambda v: v.view_mode == modo)
            self.assertFalse(
                outra.view_id,
                'a ação Livros fixou uma view de %s; era para seguir a padrão'
                % modo)
