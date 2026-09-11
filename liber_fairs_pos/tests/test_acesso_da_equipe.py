# -*- coding: utf-8 -*-
"""O acesso da equipe do evento: nasce com ele e morre com ele.

Três regras, e as três vieram do dono:

  - o papel se decide na linha (operador ou gerente), e não na tela de
    usuários -- ninguém vai à administração por causa de uma feira de três
    dias;
  - fechou o evento, esse povo não tem mais acesso;
  - e o gerente tem acesso à FEIRA DELE, não às dos outros.
"""
from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs_pos')
class TestAcessoDaEquipe(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.armazem = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.livro = cls.env['product.product'].create({
            'name': 'Título do Acesso', 'type': 'consu', 'is_storable': True})
        cls.env['stock.quant']._update_available_quantity(
            cls.livro, cls.armazem.lot_stock_id, 60)
        cls.campo = cls.env.ref('liber_fairs_pos.group_fair_field')
        cls.gerente = cls.env.ref('liber_fairs.group_fair_manager')
        cls.pdv = cls.env.ref('point_of_sale.group_pos_user')
        cls.balcao = cls.env.ref('liber_fairs_pos.group_fair_cashier')

    def _pessoa(self, nome):
        """Um contato COM conta: é quem pode receber acesso."""
        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': nome, 'login': nome.lower().replace(' ', '_'),
                'password': nome.lower().replace(' ', '_'),
                'company_id': self.company.id,
                'company_ids': [(6, 0, [self.company.id])],
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        return usuario.partner_id, usuario

    def _feira(self, nome, qty=6):
        return self.env['event.fair'].create({
            'name': nome, 'date_start': date.today(),
            'date_end': date.today(), 'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.livro.id, 'qty_planned': qty})]})

    def _escalar(self, fair, partner, role='operator'):
        return self.env['event.fair.cashier'].create({
            'fair_id': fair.id, 'partner_id': partner.id, 'role': role})

    # --- o acesso -------------------------------------------------------
    def test_planning_the_event_lets_the_team_in(self):
        contato, usuario = self._pessoa('Abou Mourad')
        fair = self._feira('Feira do Acesso')
        linha = self._escalar(fair, contato)
        self.assertFalse(linha.access_granted,
                         "Evento em rascunho não dá acesso a ninguém")

        fair.action_plan()

        linha.invalidate_recordset()
        self.assertTrue(linha.access_granted)
        self.assertIn(self.balcao, usuario.all_group_ids,
                      "O assistente entra para VENDER: o caixa é o acesso "
                      "dele")
        self.assertIn(self.pdv, usuario.all_group_ids,
                      "E o grupo do balcão carrega o papel de PDV junto")
        self.assertNotIn(self.campo, usuario.all_group_ids,
                         "E só o caixa: nada de aplicativo de eventos")
        self.assertNotIn(self.gerente, usuario.all_group_ids,
                         "Operador não é gerente")
        self.assertEqual(linha.access_state, 'granted')

    def test_the_manager_on_site_is_not_the_house_manager(self):
        """O gerente de campo é CIRCUNSTANCIAL, e a régua mudou aqui.

        Ele toca o evento na praça e não faz parte do planejamento: não decide
        o que vai, não decide quando vai e -- principalmente -- não decide
        quanto cada um ganha. Dar-lhe o papel de Administrador de Feiras da
        casa trazia as três coisas junto.
        """
        contato, usuario = self._pessoa('Alejandra Luciani')
        fair = self._feira('Feira da Gerente')
        self._escalar(fair, contato, role='manager')
        fair.action_plan()
        self.assertIn(self.campo, usuario.all_group_ids,
                      "É o grupo que o prende ao evento dele")
        self.assertIn(self.pdv, usuario.all_group_ids,
                      "E ele também opera caixa")
        self.assertNotIn(self.gerente, usuario.all_group_ids,
                         "O papel da CASA não é dele: quem planeja é outro")

    def test_the_manager_on_site_cannot_set_what_people_earn(self):
        """Juiz em causa própria: a combinação é anterior ao evento."""
        contato, usuario = self._pessoa('Gerente Sem Cofre')
        fair = self._feira('Feira do cofre')
        linha = self._escalar(fair, contato, role='manager')
        fair.action_plan()
        self.env.invalidate_all()
        with self.assertRaises(Exception):
            linha.with_user(usuario).write({'commission_pc': 30.0})
        with self.assertRaises(Exception):
            linha.with_user(usuario).write({'daily_rate': 500.0})

    def test_the_manager_on_site_reaches_the_other_registers(self):
        """Balcão travado se resolve na praça, e não por telefone com a casa."""
        gerente, usuario = self._pessoa('Gerente que Destrava')
        colega, _u = self._pessoa('Colega de Balcão')
        fair = self._feira('Feira de dois caixas')
        self._escalar(fair, gerente, role='manager')
        linha_colega = self._escalar(fair, colega)
        fair.action_plan()
        fair.action_open_pos()
        self.env.invalidate_all()

        visiveis = self.env['pos.config'].with_user(usuario).search([])

        self.assertIn(linha_colega.pos_config_id, visiveis,
                      "O gerente entra no caixa da colega para resolver")

    def test_the_assistant_sees_her_own_event_and_nothing_else(self):
        """Ela pode ficar SOZINHA na praça, e caixa de livro não espera.

        Ver o evento dela é o que permite conferir a chegada. O que ela não vê
        é o resto: perda, grade de outro evento, evento de outra gente.
        """
        contato, usuario = self._pessoa('Só Balcão')
        fair = self._feira('Feira do balcão')
        outra = self._feira('Feira de outra gente')
        self._escalar(fair, contato)
        fair.action_plan()
        outra.action_plan()
        self.env.invalidate_all()

        visiveis = self.env['event.fair'].with_user(usuario).search([])

        self.assertEqual(visiveis, fair, "A dela, e só a dela")
        with self.assertRaises(Exception):
            self.env['event.fair.loss'].with_user(usuario).search([])

    def test_the_assistant_can_check_the_arrival_alone(self):
        """Sem gerente por perto, a carga ainda entra na mesa."""
        contato, usuario = self._pessoa('Recebe Sozinha')
        fair = self._feira('Feira da chegada')
        self._escalar(fair, contato)
        fair.action_plan()
        saida = fair.action_ship()
        saida.action_assign()
        for move in saida.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        saida.button_validate()
        self.env.invalidate_all()

        chegada = self.env['stock.picking'].with_user(usuario).search(
            [('fair_id', '=', fair.id), ('fair_operation', '=', 'receipt')])
        self.assertTrue(chegada, "A chegada da feira dela tem de aparecer")
        chegada.action_fair_check()

        self.assertTrue(all(p.state == 'done' for p in chegada),
                        "E ela conclui a conferência sozinha")

    def test_a_contact_without_an_account_works_the_counter_anyway(self):
        contato = self.env['res.partner'].create({'name': 'Sem conta'})
        fair = self._feira('Feira sem conta')
        linha = self._escalar(fair, contato)
        fair.action_plan()
        linha.invalidate_recordset()
        self.assertEqual(linha.access_state, 'no_account')
        self.assertFalse(linha.access_granted,
                         "Sem conta não há o que conceder, e isso não é erro")

    def test_closing_the_event_takes_the_access_back(self):
        """Fechou o evento, esse povo não tem mais acesso."""
        contato, usuario = self._pessoa('Abou de Volta')
        fair = self._feira('Feira que fecha')
        linha = self._escalar(fair, contato, role='manager')
        fair.action_plan()
        self.assertIn(self.campo, usuario.group_ids)

        fair.state = 'returned'

        linha.invalidate_recordset()
        usuario.invalidate_recordset()
        self.assertFalse(linha.access_granted)
        self.assertNotIn(self.campo, usuario.all_group_ids)
        self.assertNotIn(self.gerente, usuario.all_group_ids)
        self.assertEqual(linha.access_state, 'ended')

    def test_who_still_works_another_event_keeps_the_key(self):
        """Duas feiras ao mesmo tempo: encerrar uma não tranca a outra."""
        contato, usuario = self._pessoa('Dois Eventos')
        uma = self._feira('Feira que acaba')
        outra = self._feira('Feira que segue')
        self._escalar(uma, contato)
        self._escalar(outra, contato)
        uma.action_plan()
        outra.action_plan()

        uma.state = 'returned'

        usuario.invalidate_recordset()
        self.assertIn(self.pdv, usuario.all_group_ids,
                      "Ele ainda trabalha a outra feira")

    def test_taking_somebody_off_the_team_takes_the_access(self):
        contato, usuario = self._pessoa('Saiu da Escala')
        fair = self._feira('Feira da escala')
        linha = self._escalar(fair, contato)
        fair.action_plan()
        linha.unlink()
        usuario.invalidate_recordset()
        self.assertNotIn(self.pdv, usuario.all_group_ids)

    # --- o que cada um vê ------------------------------------------------
    def test_the_manager_only_sees_his_own_event(self):
        """O gerente tem acesso à feira DELE."""
        contato, usuario = self._pessoa('Só a Minha')
        minha = self._feira('Minha feira')
        alheia = self._feira('Feira dos outros')
        self._escalar(minha, contato, role='manager')
        minha.action_plan()
        alheia.action_plan()
        self.env.invalidate_all()

        visiveis = self.env['event.fair'].with_user(usuario).search([])
        self.assertIn(minha, visiveis)
        self.assertNotIn(alheia, visiveis,
                         "Feira de outra equipe não é assunto dele")

    def test_the_house_commercial_keeps_seeing_everything(self):
        """A regra prende a EQUIPE, não o Comercial da casa.

        Odoo soma com OU as regras dos grupos de cada pessoa: quem não está no
        grupo da equipe não é alcançado pela regra dela.
        """
        papel = self.env.ref('liber_roles.group_comercial_gerente',
                             raise_if_not_found=False)
        if not papel:
            self.skipTest('liber_roles não está instalado neste banco')
        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Comercial da casa', 'login': 'comercial_casa',
                'password': 'comercial_casa',
                'company_id': self.company.id,
                'company_ids': [(6, 0, [self.company.id])],
                'group_ids': [(6, 0, [papel.id])]})
        uma = self._feira('Feira A')
        outra = self._feira('Feira B')
        uma.action_plan()
        outra.action_plan()
        self.env.invalidate_all()
        visiveis = self.env['event.fair'].with_user(usuario).search([])
        self.assertIn(uma, visiveis)
        self.assertIn(outra, visiveis)

    def test_what_the_person_already_had_is_not_taken_away(self):
        """O caixa da loja que veio ajudar não perde o PDV do dia a dia.

        Tira-se o que foi DADO, e nada além. Sem essa conta, encerrar a feira
        arrancaria o acesso que a pessoa já tinha por conta própria.
        """
        contato, usuario = self._pessoa('Já era do PDV')
        usuario.sudo().write({'group_ids': [(4, self.pdv.id)]})
        fair = self._feira('Feira de quem já tinha')
        linha = self._escalar(fair, contato)
        fair.action_plan()
        self.assertIn(self.balcao, linha.granted_group_ids,
                      "O grupo do balcão da FEIRA é nosso de dar")
        self.assertNotIn(self.pdv, linha.granted_group_ids,
                         "Mas o papel de PDV ele já tinha: não é dádiva nossa")

        fair.state = 'returned'

        usuario.invalidate_recordset()
        self.assertNotIn(self.balcao, usuario.all_group_ids,
                         "O que demos, tiramos")
        self.assertIn(self.pdv, usuario.all_group_ids,
                      "E não se tira o que não se deu: ele continua operando "
                      "o PDV do dia a dia")


@tagged('post_install', '-at_install', 'liber_fairs_pos')
class TestVitrineVeOBalcao(TransactionCase):
    """O manual fala do caixa metade do tempo; a demonstração tem de ter um."""

    def test_the_public_visitor_reaches_the_register_app(self):
        visitante = self.env.ref('liber_roles.group_visitante',
                                 raise_if_not_found=False)
        if not visitante:
            self.skipTest('liber_roles não está instalado neste banco')
        pdv = self.env.ref('point_of_sale.group_pos_user')

        self.assertIn(pdv, visitante.all_implied_ids,
                      "Sem isto, o manual fala de uma tela que não existe")

    def test_but_the_visitor_still_does_not_write(self):
        """Ver o balcão, sim; abrir sessão, não. A trava é no ORM."""
        visitante = self.env.ref('liber_roles.group_visitante',
                                 raise_if_not_found=False)
        if not visitante:
            self.skipTest('liber_roles não está instalado neste banco')
        from odoo.addons.liber_roles.models.ir_model_access import (
            VISITOR_WRITABLE_MODELS)

        self.assertNotIn('pos.session', VISITOR_WRITABLE_MODELS)
        self.assertNotIn('pos.order', VISITOR_WRITABLE_MODELS)


@tagged('post_install', '-at_install', 'liber_fairs_pos')
class TestOBalcaoVemComAFeira(TransactionCase):
    """Instalar o PDV não o faz aparecer: o app é de quem tem o papel dele."""

    def test_whoever_works_fairs_sees_the_register_app(self):
        feiras = self.env.ref('liber_fairs.group_fair_user')
        pdv = self.env.ref('point_of_sale.group_pos_user')

        self.assertIn(pdv, feiras.all_implied_ids,
                      "Feira vende no balcão: quem monta o evento precisa "
                      "alcançar o caixa")

    def test_the_house_roles_reach_it_through_the_bridge(self):
        papel = self.env.ref('liber_roles.group_comercial_gerente',
                             raise_if_not_found=False)
        if not papel:
            self.skipTest('liber_roles não está instalado neste banco')
        pdv = self.env.ref('point_of_sale.group_pos_user')

        self.assertIn(pdv, papel.all_implied_ids,
                      "O comercial trabalha feira, e a ponte já o liga ao "
                      "papel de Feiras")
