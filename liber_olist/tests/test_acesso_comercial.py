# -*- coding: utf-8 -*-
"""O comercial atualiza o espelho e despacha (24/08/2026).

Até aqui só a administração escrevia, e a equipe batia em "Você não tem
permissões para criar registros de Espelho de pedido do Olist" ao clicar em
Pedidos do Olist. O cron reescreve esse espelho toda noite: negar o mesmo ato
sob demanda travava o trabalho sem proteger nada.

O que este teste guarda é a FRONTEIRA, não a permissão: o Operador escreve nos
espelhos e despacha; a ficha da CONTA — token e a trava "Somente leitura", que
é o que segura os clones — continua fora do alcance dele.

Cada verificação roda com `with_user`, e o cache da transação é invalidado
entre elas: sem isso a varredura mede o primeiro usuário e repete a resposta.
"""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAcessoComercial(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist ACL", 'company_id': cls.env.company.id,
            'token': "TOKEN-ACL", 'read_only': True, 'stock_reserve': 0})
        cls.assistente = cls.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': "Assistente comercial",
                'login': 'comercial_acl',
                'password': 'comercial_acl',
                'company_id': cls.env.company.id,
                'company_ids': [(6, 0, [cls.env.company.id])],
                'group_ids': [(4, cls.env.ref(
                    'liber_roles.group_comercial_assistente').id)],
            })

    def _como_assistente(self, modelo):
        self.env.invalidate_all()
        return self.env[modelo].with_user(self.assistente)

    def test_the_assistant_can_refresh_the_mirror(self):
        """Criar e escrever no espelho: é o que o botão de ler pedidos faz."""
        pedido = self._como_assistente('olist.order').create({
            'account_id': self.account.id, 'olist_id': 'ACL-1',
            'numero': "ACL-1", 'situacao': "Aprovado",
            'data_pedido': '2026-08-24'})
        self.assertTrue(pedido.id)
        pedido.write({'situacao': "Enviado"})
        self.assertEqual(pedido.situacao, "Enviado")

    def test_the_assistant_can_write_the_lines_and_the_channel(self):
        """Ler o detalhe grava itens e DESCOBRE canal — os dois precisam passar."""
        pedido = self._como_assistente('olist.order').create({
            'account_id': self.account.id, 'olist_id': 'ACL-2',
            'numero': "ACL-2", 'data_pedido': '2026-08-24'})
        pedido.write({'line_ids': [(0, 0, {
            'codigo': "9786666666663", 'descricao': "Livro",
            'quantidade': 1, 'valor_unitario': 30.0})]})
        self.assertEqual(len(pedido.line_ids), 1)
        canal = self.env['olist.channel'].with_user(
            self.assistente)._find_or_create(self.account, "Mercado Livre")
        self.assertTrue(canal.id)

    def test_the_account_stays_out_of_reach(self):
        """A fronteira: a conta guarda o token e a trava do clone."""
        conta = self._como_assistente('olist.account').browse(self.account.id)
        self.assertTrue(conta.name, "ler a conta é permitido — a tela precisa")
        with self.assertRaises(AccessError):
            conta.write({'read_only': False})

    def test_the_token_never_reads(self):
        """Trava de campo, não de modelo: nem lendo a ficha o token aparece."""
        conta = self._como_assistente('olist.account').browse(self.account.id)
        with self.assertRaises(AccessError):
            conta.token          # noqa: B018 — o acesso É o teste

    def test_the_assistant_dispatches_end_to_end(self):
        """O despacho inteiro no perfil do assistente — a decisão de 24/08.

        "Tarefa de baixo custo e pouca decisão para um gerente." O caminho
        atravessa quatro modelos de donos diferentes: a venda (comercial), a
        fatura do XML (faturamento), a transferência na caixa Marketplaces
        (estoque) e o anexo. É aqui que um direito faltando aparece —
        o import é uma transação só, e ela falha inteira.
        """
        livro = self.env['product.product'].create({
            'name': "Livro do Comercial", 'barcode': "9787777777776",
            'type': 'consu', 'is_storable': True, 'list_price': 25.0})
        armazem = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        self.env['stock.quant'].sudo().create({
            'product_id': livro.id,
            'location_id': armazem.lot_stock_id.id,
            'inventory_quantity': 5,
        }).action_apply_inventory()
        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "acl.xml",
            'olist_nota_id': '990', 'olist_account_id': self.account.id,
            'danfe_no': '990', 'file_create_date': '2026-08-24'})
        self.env['nfe.xml.items'].create({
            'soc_xml_id': painel.id, 'ks_product_id': livro.id,
            'ks_product_name': "Livro", 'ks_product_qty': 2,
            'ks_price': 25.0, 'ks_product_barcode': livro.barcode})
        pedido = self.env['olist.order'].create({
            'account_id': self.account.id, 'olist_id': 'ACL-9',
            'numero': "ACL-9", 'situacao': "Aprovado",
            'cliente_nome': "Comprador do comercial",
            'data_pedido': '2026-08-24', 'id_nota_fiscal': '990',
            'detalhe_lido_em': '2026-08-24 12:00:00',
            'line_ids': [(0, 0, {'codigo': livro.barcode,
                                 'descricao': "Livro", 'quantidade': 2,
                                 'valor_unitario': 25.0,
                                 'product_id': livro.id})]})

        como_ele = self._como_assistente('olist.order').browse(pedido.id)
        self.assertTrue(como_ele._import_to_odoo())
        self.assertEqual(como_ele.sale_order_id.state, 'sale')
        self.assertTrue(como_ele.invoice_id)
        self.assertEqual(como_ele.invoice_id.state, 'posted')
        # A entrega nasce Pronta na caixa Marketplaces: é o trabalho que fica
        # com a equipe, e validá-la também tem de caber no perfil.
        saida = como_ele.sale_order_id.picking_ids
        self.assertEqual(saida.state, 'assigned')
        for movimento in saida.move_ids:
            movimento.quantity = movimento.product_uom_qty
        saida.button_validate()
        self.assertEqual(saida.state, 'done')

    def test_the_door_belongs_to_the_commercial(self):
        """O app Olist não aparece para quem não opera o marketplace.

        O Financeiro o via na home sem ter o que fazer lá (24/08/2026). Menu
        é porta: fechá-la no RAMO basta, porque o Odoo não desenha filho de
        menu invisível — e é o que este teste mede, do lado de dentro e do
        lado de fora.
        """
        menu = self.env.ref('liber_olist.menu_olist_root')
        financeiro = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': "Assistente financeiro",
                'login': 'financeiro_acl',
                'company_id': self.env.company.id,
                'company_ids': [(6, 0, [self.env.company.id])],
                'group_ids': [(4, self.env.ref(
                    'liber_roles.group_financeiro_assistente').id)],
            })
        # Medido pelo `load_menus`, que é o que a BARRA monta — nem o `search`
        # (devolve tudo para todos) nem o `_filter_visible_menus` sozinho
        # (olha o grupo de cada menu, não a corrente): quem descarta o filho
        # órfão é o load_menus, que caminha a partir das raízes visíveis e
        # joga fora o que não pertence a app nenhum. Medir com o instrumento
        # errado dá verde com a porta escancarada — foi o que aconteceu duas
        # vezes ao escrever este teste.
        filhos = self.env['ir.ui.menu'].search([('parent_id', '=', menu.id)])
        self.assertTrue(filhos, "o app tem filhos; senão o teste não prova nada")

        do_financeiro = self.env['ir.ui.menu'].with_user(
            financeiro).load_menus(False)
        self.assertNotIn(menu.id, do_financeiro,
                         "o marketplace é operação comercial")
        for filho in filhos:
            self.assertNotIn(filho.id, do_financeiro,
                             "porta fechada fecha o ramo: %s" % filho.name)

        self.env.invalidate_all()
        do_comercial = self.env['ir.ui.menu'].with_user(
            self.assistente).load_menus(False)
        self.assertIn(menu.id, do_comercial, "o comercial continua entrando")
        self.assertTrue(
            all(f.id in do_comercial for f in filhos),
            "e entra no app inteiro, não só na porta")

    def test_the_assistant_cannot_erase_history(self):
        """Arquivar é escrita; apagar não se concede — o espelho é registro."""
        pedido = self.env['olist.order'].create({
            'account_id': self.account.id, 'olist_id': 'ACL-3',
            'numero': "ACL-3", 'data_pedido': '2026-08-24'})
        como_ele = self._como_assistente('olist.order').browse(pedido.id)
        como_ele.write({'active': False})     # arquivar, sim
        self.assertFalse(como_ele.active)
        with self.assertRaises(AccessError):
            como_ele.unlink()
