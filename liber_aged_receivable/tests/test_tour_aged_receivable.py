# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged('post_install', '-at_install')
class TestTourAgedReceivable(HttpCase):
    """O ORM mede o que o teste pediu; a tela mede o que a tela pede.

    Aqui se prova o que o TransactionCase não alcança: que o menu existe para
    quem tem o perfil do Financeiro (e não só para o admin, que passa em
    tudo), que a lista chega agrupada por cliente, e que os botões de pular
    renderizam na linha.
    """

    def test_tour(self):
        company = self.env.company
        conta = self.env['account.account'].search([
            ('account_type', '=', 'asset_receivable'),
            ('company_ids', 'in', company.id)], limit=1)
        diario = self.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', company.id)], limit=1)
        receita = self.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_ids', 'in', company.id)], limit=1)
        if not (conta and diario and receita):
            self.skipTest('a empresa deste banco não tem o plano de contas '
                          'mínimo para encenar o relatório')

        parceiro = self.env['res.partner'].create({'name': 'Livraria do Tour'})
        # Uma FATURA a vencer, e nao um lancamento solto: o tour vai pedir
        # "Registrar pagamento" nela, e o assistente do Odoo so liquida
        # documento. A vencer porque e o filtro com que a tela abre.
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': parceiro.id,
            'company_id': company.id,
            'invoice_date': fields.Date.today(),
            'invoice_date_due': fields.Date.today() + timedelta(days=30),
            'invoice_line_ids': [(0, 0, {
                'name': 'livro', 'quantity': 1, 'price_unit': 500.0,
                'account_id': receita.id})],
        })
        move.action_post()

        # A senha igual ao login é o que o `start_tour` espera. E o usuário
        # leva o perfil de quem vai usar a tela -- não o admin: admin passa
        # em tudo e não prova nada sobre o perfil.
        grupos = [
            self.env.ref('base.group_user').id,
            self.env.ref('account.group_account_user').id,
        ]
        readonly = self.env.ref('account.group_account_readonly', False)
        if readonly:
            grupos.append(readonly.id)
        self.env['res.users'].create({
            'name': 'Cobrança do Tour',
            'login': 'cobranca_tour',
            'password': 'cobranca_tour',
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            # O tour acha o item do menu Acoes pelo texto, em ingles.
            'lang': 'en_US',
            'group_ids': [(6, 0, grupos)],
        })
        self.start_tour('/odoo', 'liber_aged_receivable_tour',
                        login='cobranca_tour')
