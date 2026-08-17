# -*- coding: utf-8 -*-
"""Comercial e Logística são duas funções, e a separação tem de custar algo.

Separar dois departamentos num sistema de acesso é fácil de escrever e fácil
de mentir: basta criar o grupo novo e não tirar nada de ninguém. O que este
teste trava são os dois lados da conta.

O lado de cima: a Logística abre o Inventário e não abre o comercial.

O lado de baixo, que é o perigoso: o Comercial perdeu o app Inventário mas
NÃO pode ter perdido a consignação junto. O código da casa cria stock.picking
como o usuário -- confirmar uma remessa (liber_soc_moves) e rodar um acerto
(liber_soc_settlement) gravam picking em nome de quem clicou --, então tirar o
grupo de estoque do Comercial sem mais nada quebraria a operação com
AccessError no meio do fluxo. É por isso que o Comercial ficou com um grupo
estreito no lugar do app inteiro, e é isso que os testes de regressão daqui
verificam: a remessa ainda sai.
"""

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_roles')
class TestLogisticaEComercial(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        company = cls.env.company

        def _usuario(nome, login, funcao):
            return Users.create({
                'name': nome, 'login': login,
                'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
                'group_ids': [(4, cls.env.ref('liber_roles.%s' % funcao).id)],
            })

        cls.logistica = _usuario('Logística', 'logistica@liber.test',
                                 'group_logistica_assistente')
        cls.logistica_gerente = _usuario('Logística Gerente',
                                         'logistica.gerente@liber.test',
                                         'group_logistica_gerente')
        cls.comercial = _usuario('Comercial', 'comercial.log@liber.test',
                                 'group_comercial_assistente')

        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.product = cls.env['product.product'].create({
            'name': 'Grande Sertão: Veredas', 'type': 'consu',
            'is_storable': True, 'list_price': 60.0})
        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria da Esquina', 'is_company': True})
        cls.env.flush_all()
        cls.env.registry.clear_cache()

    # -- helpers ------------------------------------------------------------
    def _menus_visiveis(self, usuario):
        """Os menus que o usuário realmente vê.

        A pergunta é feita por `load_menus`, não por `search`: `search` em
        ir.ui.menu NÃO filtra por grupo, então um teste escrito sobre ele
        passa com qualquer configuração de acesso -- inclusive com a errada.
        """
        dados = self.env(user=usuario.id, su=False)['ir.ui.menu'].load_menus(False)
        visiveis = {int(k) for k in dados if str(k).isdigit()}
        self.assertTrue(visiveis, 'load_menus não devolveu menu nenhum')
        return visiveis

    def _assert_menu(self, usuario, xmlid, rotulo, visivel):
        menu = self.env.ref(xmlid, raise_if_not_found=False)
        if not menu:
            self.skipTest('menu %s não existe nesta base' % xmlid)
        presente = menu.id in self._menus_visiveis(usuario)
        if visivel:
            self.assertTrue(presente, '%s sumiu do menu de %s'
                            % (rotulo, usuario.name))
        else:
            self.assertFalse(presente, '%s aparece no menu de %s e não deveria'
                             % (rotulo, usuario.name))

    def _agreement(self):
        agr = self.env['consignment.agreement'].create({
            'partner_id': self.partner.id,
            'company_id': self.env.company.id,
            'date_start': fields.Date.context_today(self.env.user),
        })
        agr.action_activate()
        return agr

    # -- a Logística existe e é o depósito ----------------------------------
    def test_logistica_abre_o_inventario(self):
        """A função nova serve para uma coisa só, e ela tem de estar lá."""
        self._assert_menu(self.logistica, 'stock.menu_stock_root',
                          'Inventário', visivel=True)

    def test_logistica_nao_e_comercial(self):
        """"Somente o Inventário" é uma promessa, e este é o corte.

        Se um dia alguém acrescentar um grupo aqui por conveniência ("é só
        para ele ver o pedido"), a Logística volta a ser Comercial e ninguém
        percebe. Este teste é o freio.
        """
        for rotulo, xmlid in (
                ('Vendas', 'sale.menu_sale_order'),
                ('Consignação', 'liber_soc_agreements.menu_consignment_root'),
                ('Contabilidade', 'account.menu_finance'),
                ('Compras', 'purchase.menu_purchase_root')):
            self._assert_menu(self.logistica, xmlid, rotulo, visivel=False)
        # Fora da lista de propósito: o app Site. Ele é aberto a `base.group_user`
        # no Odoo 19 -- todo empregado o vê, a Logística inclusive, e cobrá-lo
        # aqui seria cobrar da função uma coisa que não é dela.

    def test_logistica_valida_a_transferencia_da_consignacao(self):
        """O depósito despacha a remessa -- é literalmente o trabalho dele.

        O `action_release` do comercial "entrega para a logística" (o comentário
        está no código): cria o COM/MOV/ e reserva. Validar é do armazém, e sem este
        teste a promessa fica só no comentário.
        """
        self.env['stock.quant']._update_available_quantity(
            self.product, self.stock_loc, 20)
        agreement = self._agreement()
        cr_move = self.env['consignment.move'].create({
            'partner_id': self.partner.id, 'move_kind': 'shipment',
            'line_ids': [(0, 0, {'product_id': self.product.id,
                                 'product_uom_qty': 10})],
        })
        cr_move.action_confirm()
        cr_move.action_release()
        self.env.flush_all()

        picking = self.env(user=self.logistica.id, su=False)['stock.picking'].browse(
            cr_move.picking_id.id)
        picking.button_validate()
        self.assertEqual(picking.state, 'done',
                         'a logística não conseguiu validar a remessa')
        self.assertEqual(agreement.on_shelf_qty, 10)

    def test_logistica_gerente_configura_o_deposito(self):
        """O nível gerente é quem mexe na planta: armazém e localização."""
        env = self.env(user=self.logistica_gerente.id, su=False)
        local = env['stock.location'].create({
            'name': 'Corredor de teste', 'usage': 'internal',
            'location_id': self.stock_loc.id,
        })
        self.assertTrue(local.id)

        with self.assertRaises(AccessError, msg=(
                'o assistente de logística criou localização: o nível gerente '
                'deixou de significar alguma coisa')):
            self.env(user=self.logistica.id, su=False)['stock.location'].create({
                'name': 'Corredor proibido', 'usage': 'internal',
                'location_id': self.stock_loc.id,
            })

    # -- o Comercial devolveu o app, e não a operação -----------------------
    def test_comercial_nao_tem_mais_o_app_inventario(self):
        """A separação pedida: quem vende não entra no depósito."""
        self._assert_menu(self.comercial, 'stock.menu_stock_root',
                          'Inventário', visivel=False)

    def test_comercial_nao_faz_ajuste_de_inventario(self):
        """O que o app trazia junto, e era o problema.

        Com stock.group_stock_user o comercial podia reescrever o saldo físico
        de qualquer produto pela tela de contagem. É a diferença entre operar a
        consignação e mexer no estoque da casa.
        """
        quant = self.env['stock.quant'].create({
            'product_id': self.product.id,
            'location_id': self.stock_loc.id,
            'inventory_quantity': 5,
        })
        self.env.flush_all()
        with self.assertRaises(AccessError, msg=(
                'o comercial ainda escreve em stock.quant: o app Inventário '
                'saiu do menu mas não saiu do acesso')):
            self.env(user=self.comercial.id, su=False)['stock.quant'].browse(
                quant.id).write({'inventory_quantity': 99})

    def test_comercial_ainda_solta_a_remessa(self):
        """A REGRESSÃO que importa, e o motivo de tudo isto existir.

        Confirmar e soltar uma remessa GRAVA um stock.picking em nome de quem
        clicou (liber_soc_moves._create_picking). Se a separação tivesse sido
        feita só tirando o grupo de estoque do Comercial, este teste morreria
        com AccessError -- e morreria em produção, no meio de uma campanha.
        """
        self.env['stock.quant']._update_available_quantity(
            self.product, self.stock_loc, 20)
        self._agreement()
        self.env.flush_all()

        env = self.env(user=self.comercial.id, su=False)
        cr_move = env['consignment.move'].create({
            'partner_id': self.partner.id, 'move_kind': 'shipment',
            'line_ids': [(0, 0, {'product_id': self.product.id,
                                 'product_uom_qty': 6})],
        })
        cr_move.action_confirm()
        cr_move.action_release()

        self.assertTrue(cr_move.picking_id,
                        'o comercial confirmou a remessa e nenhum picking '
                        'nasceu')
        self.assertTrue(cr_move.picking_id.name.startswith('COM/MOV/'))
        self.assertEqual(cr_move.state, 'confirmed')

    def test_comercial_ainda_valida_o_picking_do_acerto(self):
        """O acerto não só cria o picking: ele valida na hora.

        `_create_shelf_outflow` (liber_soc_settlement) faz create + confirm +
        assign + button_validate numa tacada, tudo como o usuário. Criar já é
        coberto pelo teste acima; validar é o outro pedaço, e é o que este
        exercita -- sobre a mesma superfície de ORM, sem precisar montar um
        acerto inteiro.
        """
        self.env['stock.quant']._update_available_quantity(
            self.product, self.stock_loc, 20)
        self._agreement()
        self.env.flush_all()

        env = self.env(user=self.comercial.id, su=False)
        cr_move = env['consignment.move'].create({
            'partner_id': self.partner.id, 'move_kind': 'shipment',
            'line_ids': [(0, 0, {'product_id': self.product.id,
                                 'product_uom_qty': 4})],
        })
        cr_move.action_confirm()
        cr_move.action_release()
        picking = cr_move.picking_id
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.with_context(skip_backorder=True).button_validate()
        self.assertEqual(picking.state, 'done',
                         'o comercial não conseguiu validar a transferência '
                         'da consignação')

    # -- a migração, que é quem mexe em ficha de gente de verdade -----------
    def test_migracao_tira_o_inventario_de_quem_ja_era_comercial(self):
        """O XML muda o perfil; quem muda as fichas já existentes é a migração.

        `implied_ids` propaga para os usuários quando a implicação é CRIADA e
        nunca desfaz quando ela some. Sem a migração, todo comercial cadastrado
        antes de 31/07/2026 continuaria com o app Inventário — a separação
        existiria no repositório e não na base, que é a pior forma de existir.

        O segundo usuário deste teste é o caso que a migração não pode
        estragar: quem acumula Comercial e Logística tem direito ao Inventário
        pela segunda função, e sai daqui como entrou.
        """
        migracao = self._carrega_migracao()
        estoque = self.env.ref('stock.group_stock_user')

        acumula = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Comercial que também é do depósito',
                'login': 'acumula@liber.test',
                'company_id': self.env.company.id,
                'group_ids': [
                    (4, self.env.ref('liber_roles.group_comercial_assistente').id),
                    (4, self.env.ref('liber_roles.group_logistica_assistente').id),
                ],
            })
        # o rastro que a propagação do Odoo deixou nas fichas antigas
        (self.comercial + acumula).write({'group_ids': [(4, estoque.id)]})
        self.env.flush_all()
        self.assertIn(estoque, self.comercial.group_ids, 'setup do teste falhou')

        migracao.migrate(self.env.cr, '19.0.1.0.0')
        self.env.invalidate_all()

        self.assertNotIn(
            estoque, self.comercial.group_ids,
            'a migração não devolveu o app Inventário: o comercial antigo '
            'seguiria com o depósito na mão')
        self.assertFalse(
            self.comercial.has_group('stock.group_stock_user'),
            'o comercial ainda alcança o Inventário por implicação')
        self.assertTrue(
            acumula.has_group('stock.group_stock_user'),
            'a migração levou junto o Inventário de quem acumula Logística')

    def _carrega_migracao(self):
        """A migração não é um módulo importável (o Odoo a carrega por caminho)."""
        import importlib.util
        import os
        caminho = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'migrations', '19.0.1.1.0', 'post-comercial_sem_inventario.py')
        spec = importlib.util.spec_from_file_location('post_comercial', caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    def test_comercial_enxerga_o_estoque_do_livro(self):
        """Perder o app não é perder a pergunta.

        Os dois botões da ficha do produto ("Stock" e "Consigned") respondem
        "onde estão meus livros?" e são do comercial tanto quanto do depósito.
        Eles são gated em grupo, então o corte poderia tê-los levado junto.
        """
        env = self.env(user=self.comercial.id, su=False)
        arch = env['product.template'].get_view(view_type='form')['arch']
        for botao in ('action_view_soc_wh_stock', 'action_view_soc_consigned'):
            self.assertIn(
                botao, arch,
                'o botão %s sumiu da ficha do produto para o comercial' % botao)
