# -*- coding: utf-8 -*-
"""A feira rodada pelos perfis reais da casa, não pelo admin.

O admin passa em tudo e não prova nada sobre o perfil. Este arquivo roda o
caminho principal como GERENTE COMERCIAL (que abre a feira e despacha) e como
ASSISTENTE COMERCIAL (que está na praça e fecha o dia). É o teste que pega o
Access Error do primeiro clique: a feira mexe em stock.picking, stock.move,
stock.location e ir.sequence, e nada disso está no grupo do módulo.

Não substitui o tour, que a regra da casa pede ao CONCLUIR o módulo -- o ORM
mede o que o teste pediu, e a tela pede mais. Enquanto o módulo está em
protótipo, é o que temos.
"""
from datetime import date, timedelta

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs')
class TestFairAcl(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.product = cls.env['product.product'].create({
            'name': 'Título do ACL',
            'type': 'consu',
            'is_storable': True,
        })
        cls.env['stock.quant']._update_available_quantity(
            cls.product, cls.warehouse.lot_stock_id, 50)
        cls.today = date(2026, 9, 20)

    def _user(self, login, *xmlids):
        groups = []
        for xmlid in xmlids:
            grupo = self.env.ref(xmlid, raise_if_not_found=False)
            if not grupo:
                self.skipTest("%s não está instalado neste banco" % xmlid)
            groups.append((4, grupo.id))
        return self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': login,
                'login': login,
                'password': login,
                'company_id': self.company.id,
                'company_ids': [(6, 0, [self.company.id])],
                'group_ids': groups,
            })

    def test_the_commercial_profile_runs_the_whole_fair(self):
        """Gerente abre e despacha; assistente fecha o dia. Sem Access Error."""
        gerente = self._user('feira_gerente',
                             'liber_roles.group_comercial_gerente')
        assistente = self._user('feira_assistente',
                                'liber_roles.group_comercial_assistente')
        # Sem isto a varredura multi-perfil mede só o primeiro usuário: o
        # cache da transação carrega os direitos de quem leu primeiro.
        self.env.invalidate_all()

        fair = self.env['event.fair'].with_user(gerente).create({
            'name': 'Feira do Perfil',
            'date_start': self.today,
            'date_end': self.today,
            'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id, 'qty_planned': 8})],
        })
        fair.action_plan()
        picking = fair.action_ship()
        # A logística separa e confere: quem despacha é o comercial, quem
        # valida é o armazém, e os dois são o mesmo gerente aqui.
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()
        # a segunda perna: quem está na praça confere a chegada
        recebimento = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'receipt' and p.state != 'done')
        recebimento.action_assign()
        for move in recebimento.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        recebimento.button_validate()
        self.assertEqual(fair.qty_on_shelf, 8)

        self.env.invalidate_all()
        dia = fair.day_ids[0].with_user(assistente)
        dia.action_fill()
        dia.line_ids.qty_counted = 5
        dia.action_close()
        self.assertEqual(dia.state, 'closed')
        self.assertEqual(dia.qty_sold, 3)
        self.assertEqual(fair.qty_on_shelf, 5)

    def test_a_fair_user_cannot_open_a_fair(self):
        """Comprometer estoque da casa fora da casa é decisão de gerente."""
        assistente = self._user('feira_so_usuaria',
                                'liber_roles.group_comercial_assistente')
        self.env.invalidate_all()
        self.assertFalse(
            self.env['event.fair'].with_user(assistente).check_access_rights(
                'create', raise_exception=False),
            "O assistente opera a feira, mas não abre feira")

    def test_the_fair_team_checks_without_the_warehouse_role(self):
        """Conferir a caixa da feira não é operar o depósito.

        Quem está na praça não tem o papel de Inventário, e não deveria. O
        direito de conferir é o de feira; a escrita no estoque vai em sudo,
        com a assinatura de quem conferiu no lugar do direito.
        """
        usuario = self._user('feira_so_da_feira',
                             'liber_fairs.group_fair_manager')
        self.assertFalse(
            usuario.has_group('stock.group_stock_user'),
            "O usuário do teste não pode ter o papel de Inventário, senão "
            "o teste não prova nada")
        self.env.invalidate_all()

        # a feira é montada e despachada por quem tem esses direitos (aqui,
        # o próprio teste); o que se prova é a CONFERÊNCIA na praça
        fair = self.env['event.fair'].create({
            'name': 'Feira sem Inventário',
            'date_start': self.today, 'date_end': self.today,
            'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id, 'qty_planned': 5})]})
        fair.action_plan()
        saida = fair.action_ship()
        saida.action_assign()
        for move in saida.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        saida.button_validate()

        chegada = fair.picking_ids.filtered(
            lambda p: p.fair_is_arrival and p.state != 'done')
        self.assertTrue(chegada)
        chegada.with_user(usuario).action_fair_check()
        self.assertEqual(chegada.state, 'done')
        self.assertEqual(chegada.fair_checked_by_id, usuario,
                         "A assinatura é de quem conferiu, não do sudo")
        self.assertEqual(fair.qty_sent, 5)

    def test_without_the_fair_role_nobody_checks(self):
        estranho = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Sem feira', 'login': 'sem_feira',
                'password': 'sem_feira',
                'company_id': self.company.id,
                'company_ids': [(6, 0, [self.company.id])],
                'group_ids': [(4, self.env.ref('base.group_user').id)]})
        self.env.invalidate_all()
        picking = self.env['stock.picking'].search(
            [('fair_is_arrival', '=', True)], limit=1)
        if not picking:
            self.skipTest("nenhuma chegada de feira neste banco")
        with self.assertRaises(UserError):
            picking.with_user(estranho).action_fair_check()


@tagged('post_install', '-at_install', 'liber_fairs')
class TestPapeisDaCasa(TransactionCase):
    """A ponte com os papéis da casa, que roda na instalação do módulo."""

    def test_the_public_visitor_can_open_the_events_app(self):
        """A vitrine mostra o que ela documenta.

        O visitante da demonstração abre em leitura toda tela que tem manual
        publicado. Eventos ganhou manual; sem esta ponte, quem lê o manual da
        feira no site e entra na demonstração não acha o aplicativo -- o que é
        pior do que não ter o módulo.
        """
        visitante = self.env.ref('liber_roles.group_visitante',
                                 raise_if_not_found=False)
        if not visitante:
            self.skipTest('liber_roles não está instalado neste banco')
        usuario = self.env.ref('liber_fairs.group_fair_user')

        self.assertIn(usuario, visitante.all_implied_ids,
                      "O visitante tem de alcançar o aplicativo Eventos")

    def test_the_visitor_is_not_a_fair_administrator(self):
        """Olhar, sim; planejar, não -- planejar é escrever."""
        visitante = self.env.ref('liber_roles.group_visitante',
                                 raise_if_not_found=False)
        if not visitante:
            self.skipTest('liber_roles não está instalado neste banco')
        gestor = self.env.ref('liber_fairs.group_fair_manager')

        self.assertNotIn(gestor, visitante.all_implied_ids)
