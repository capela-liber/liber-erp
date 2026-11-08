# -*- coding: utf-8 -*-
"""Cada caixa de feira tem a sua gaveta, e a gaveta abre.

Escrito depois do primeiro caixa da n-1 (30/10/2026), que recusou abrir com
"Você precisa de uma conta de perdas e lucros em seu diário de caixa". Os
caixas da Edlab abriam porque NENHUM tinha Dinheiro: o PDV só o dava ao
primeiro caixa da empresa. Ver `models/res_company.py`.
"""
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .test_caixa_da_feira import TestCaixaDaFeira


@tagged('post_install', '-at_install', 'liber_fairs_pos')
class TestDinheiroDoCaixa(TestCaixaDaFeira):

    def _dinheiro(self, config):
        return config.payment_method_ids.filtered('is_cash_count')

    def test_the_register_opens_with_a_drawer(self):
        """O caminho do botão "Abrir caixa registradora", com controle de caixa."""
        fair = self._feira_na_praca()
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        config = fair.pos_config_id
        dinheiro = self._dinheiro(config)
        self.assertEqual(len(dinheiro), 1)
        self.assertTrue(config.cash_control)
        diario = dinheiro.journal_id
        self.assertEqual(diario.default_account_id,
                         self.company.fair_cash_account_id)
        self.assertEqual(
            diario.profit_account_id,
            self.company.default_cash_difference_income_account_id)
        self.assertEqual(
            diario.loss_account_id,
            self.company.default_cash_difference_expense_account_id)
        # É aqui que o caixa da n-1 parava.
        config._check_before_creating_new_session()

    def _gavetas(self):
        return self.env['pos.payment.method'].search([
            ('fair_drawer', '=', True), ('company_id', '=', self.company.id)])

    def _voltar(self, fair):
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 10
        dia.action_close()
        self._despachar_de_volta(fair.action_return())

    def test_every_register_open_at_once_gets_its_own_drawer(self):
        """O segundo caixa da empresa também tem Dinheiro -- e não cria conta."""
        uma = self._feira_na_praca()
        self._operadores(uma, 'Marta', 'Joana')
        uma.action_open_pos()
        outra = self._feira_na_praca()
        self._operadores(outra, 'Ana')
        outra.action_open_pos()
        caixas = (uma | outra).pos_config_ids
        self.assertEqual(len(caixas), 3)
        gavetas = caixas.mapped(self._dinheiro)
        self.assertEqual(len(gavetas), 3, "Caixa sem gaveta, ou gaveta dividida")
        self.assertTrue(all(gavetas.mapped('fair_drawer')))
        self.assertEqual(len(gavetas.journal_id), 3)
        self.assertEqual(gavetas.journal_id.default_account_id,
                         self.company.fair_cash_account_id)
        self.assertEqual(
            sorted(gavetas.journal_id.with_context(lang='en_US')
                   .mapped('name')),
            ['Fair cash 01', 'Fair cash 02', 'Fair cash 03'])

    def test_the_next_fair_reuses_the_drawer(self):
        """O efeito colateral que não se quer: um diário por caixa que existiu."""
        uma = self._feira_na_praca()
        self._operadores(uma, 'Marta')
        uma.action_open_pos()
        gaveta = self._dinheiro(uma.pos_config_id)
        self._voltar(uma)
        self.assertFalse(uma.with_context(
            active_test=False).pos_config_id.payment_method_ids.filtered(
                'is_cash_count'), "O caixa arquivado devolve a gaveta")

        outra = self._feira_na_praca()
        self._operadores(outra, 'Joana')
        outra.action_open_pos()
        self.assertEqual(self._dinheiro(outra.pos_config_id), gaveta)
        self.assertEqual(len(self._gavetas()), 1, "Diário novo sem precisar")
        outra.pos_config_id._check_before_creating_new_session()

    def test_a_reopened_register_takes_a_free_drawer(self):
        """Caixa reativado volta com gaveta -- não com a que outro está usando."""
        uma = self._feira_na_praca()
        self._operadores(uma, 'Marta')
        uma.action_open_pos()
        config = uma.pos_config_id
        gaveta = self._dinheiro(config)
        # O que o retorno deixa: gaveta devolvida, caixa arquivado.
        config.payment_method_ids = [(3, gaveta.id)]
        config.active = False
        outra = self._feira_na_praca()
        self._operadores(outra, 'Joana')
        outra.action_open_pos()
        self.assertEqual(self._dinheiro(outra.pos_config_id), gaveta)

        uma.action_open_pos()
        self.assertTrue(config.active)
        nova = self._dinheiro(config)
        self.assertTrue(nova)
        self.assertNotEqual(nova, gaveta)
        self.assertEqual(len(self._gavetas()), 2)

    def test_the_other_methods_are_the_ones_chosen(self):
        """Cartão é o escolhido, e não o primeiro diário de banco do núcleo."""
        banco = self.env['account.journal'].search([
            ('type', '=', 'bank'), ('company_id', '=', self.company.id)],
            limit=1)
        maquininha = self.env['pos.payment.method'].create({
            'name': 'Maquininha', 'journal_id': banco.id,
            'company_id': self.company.id})
        self.company.fair_payment_method_ids = maquininha
        fair = self._feira_na_praca()
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        config = fair.pos_config_id
        self.assertEqual(config.payment_method_ids - self._dinheiro(config),
                         maquininha)

    def test_without_the_setup_the_register_is_not_created(self):
        fair = self._feira_na_praca()
        self._operadores(fair, 'Marta')
        self.company.default_cash_difference_expense_account_id = False
        with self.assertRaisesRegex(UserError, 'Cash shortage account'):
            fair.action_open_pos()
        self.assertFalse(fair.with_context(
            active_test=False).pos_config_ids)

    def test_cash_is_not_an_other_method(self):
        fair = self._feira_na_praca()
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        with self.assertRaises(ValidationError):
            self.company.fair_payment_method_ids = self._dinheiro(
                fair.pos_config_id)

    def test_saving_the_settings_fixes_the_register_born_before(self):
        """O caixa do Tales: nasceu antes da configuração, sem as contas.

        Só o vazio se preenche; conta escolhida à mão no diário fica.
        """
        uma = self._feira_na_praca()
        self._operadores(uma, 'Marta')
        uma.action_open_pos()
        outra = self._feira_na_praca()
        self._operadores(outra, 'Joana')
        outra.action_open_pos()
        velho = self._dinheiro(uma.pos_config_id).journal_id
        velho.write({'profit_account_id': False, 'loss_account_id': False})
        escolhida = self.env['account.account'].create({
            'code': 'FEIRA09', 'name': 'Falta escolhida à mão',
            'account_type': 'expense',
            'company_ids': [(6, 0, [self.company.id])]})
        mexido = self._dinheiro(outra.pos_config_id).journal_id
        mexido.loss_account_id = escolhida
        with self.assertRaises(Exception):
            uma.pos_config_id._check_before_creating_new_session()

        self.env['res.config.settings'].create({}).execute()

        self.assertEqual(
            velho.profit_account_id,
            self.company.default_cash_difference_income_account_id)
        self.assertEqual(
            velho.loss_account_id,
            self.company.default_cash_difference_expense_account_id)
        self.assertEqual(mexido.loss_account_id, escolhida)
        uma.pos_config_id._check_before_creating_new_session()

    def test_saving_the_settings_leaves_drawer_01_ready(self):
        """A gaveta 01 existe antes da primeira feira -- uma só, por empresa."""
        self._gavetas().unlink()
        self.env['res.config.settings'].create({}).execute()
        gavetas = self._gavetas()
        self.assertEqual(len(gavetas), 1)
        self.assertEqual(gavetas.journal_id.with_context(lang='en_US').name,
                         'Fair cash 01')
        self.env['res.config.settings'].create({}).execute()
        self.assertEqual(self._gavetas(), gavetas, "Salvar de novo não cria outra")
        acao = self.env['res.config.settings'].create(
            {}).action_fair_drawers()
        self.assertEqual(self.env['account.journal'].search(acao['domain']),
                         gavetas.journal_id)

        fair = self._feira_na_praca()
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        self.assertEqual(self._dinheiro(fair.pos_config_id), gavetas,
                         "O primeiro caixa usa a gaveta que já estava pronta")

    def test_without_the_setup_saving_creates_no_drawer(self):
        self._gavetas().unlink()
        self.company.fair_cash_account_id = False
        self.env['res.config.settings'].create({}).execute()
        self.assertFalse(self._gavetas())
