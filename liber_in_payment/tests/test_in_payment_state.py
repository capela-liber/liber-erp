# -*- coding: utf-8 -*-
"""O estado "Em pagamento" no Community.

Regra da casa: pagamento confirmado e dinheiro ainda na conta de pendentes
NAO e dinheiro no banco. A fatura diz "Em pagamento" ate o extrato conciliar.
O core Community responde 'paid' no gancho; este modulo responde 'in_payment'
-- por empresa, desligavel para quem nao concilia extrato.

Empresa: reaproveita-se a do ambiente -- criar res.company em teste com
account instalado morre no NOT NULL de fiscalyear (licao de 12/08).
"""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestInPaymentState(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.use_in_payment_state = True
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente do Teste'})
        cls.income = cls.env['account.account'].create({
            'name': 'Receita de teste', 'code': 'TIP.RECEITA',
            'account_type': 'income',
        })
        cls.outstanding = cls.env['account.account'].create({
            'name': 'Recebimentos pendentes de teste', 'code': 'TIP.PENDENTE',
            'account_type': 'asset_current', 'reconcile': True,
        })
        cls.journal = cls.env['account.journal'].create({
            'name': 'Banco do teste', 'code': 'TIPBK', 'type': 'bank',
        })
        cls.journal.inbound_payment_method_line_ids.payment_account_id = \
            cls.outstanding

    def _fatura_paga(self):
        """Cria, lanca e paga uma fatura pelo diario do teste."""
        inv = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Servico', 'quantity': 1, 'price_unit': 100.0,
                'account_id': self.income.id, 'tax_ids': False,
            })],
        })
        inv.action_post()
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=inv.ids,
        ).create({'journal_id': self.journal.id})
        wizard.action_create_payments()
        return inv

    def test_pagamento_pendente_fica_em_pagamento(self):
        """Caminho feliz: pagamento na conta de pendentes -> Em pagamento."""
        inv = self._fatura_paga()
        self.assertEqual(inv.payment_state, 'in_payment',
                         "com pendente nao conciliado a fatura nao pode ser 'paid'")

    def test_empresa_com_interruptor_desligado_paga_na_hora(self):
        """Borda: empresa que nao concilia extrato (o caso n-1) desliga o
        interruptor e volta ao Community puro: 'paid' imediato."""
        self.company.use_in_payment_state = False
        inv = self._fatura_paga()
        self.assertEqual(inv.payment_state, 'paid')

    def test_marcar_pago_na_mao_nao_libera(self):
        """Guarda: marcar o PAGAMENTO como Pago na mao nao vira a fatura --
        o caminho para 'paid' e a conciliacao da linha pendente."""
        inv = self._fatura_paga()
        inv.matched_payment_ids.action_validate()
        self.assertEqual(inv.payment_state, 'in_payment')

    def test_fatura_zerada_nao_passa_por_pagamento(self):
        """Limite: fatura de total zero nasce quitada sem pagamento nenhum --
        o gancho nao pode transforma-la em 'in_payment'."""
        inv = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Cortesia', 'quantity': 1, 'price_unit': 0.0,
                'account_id': self.income.id, 'tax_ids': False,
            })],
        })
        inv.action_post()
        self.assertEqual(inv.payment_state, 'paid')

    def test_conciliacao_do_pendente_libera_a_fatura(self):
        """O fim do fluxo: conciliada a linha pendente (aqui contra um
        lancamento manual que faz as vezes do extrato), a fatura enfim
        exibe 'paid'."""
        inv = self._fatura_paga()
        pendente = inv.matched_payment_ids.move_id.line_ids.filtered(
            lambda l: l.account_id == self.outstanding)
        contra = self.env['account.move'].create({
            'move_type': 'entry',
            'line_ids': [
                (0, 0, {'account_id': self.outstanding.id, 'debit': 0.0,
                        'credit': 100.0, 'name': 'extrato faz-de-conta'}),
                (0, 0, {'account_id': self.journal.default_account_id.id,
                        'debit': 100.0, 'credit': 0.0, 'name': 'contrapartida'}),
            ],
        })
        contra.action_post()
        (pendente + contra.line_ids.filtered(
            lambda l: l.account_id == self.outstanding)).reconcile()
        self.assertEqual(inv.payment_state, 'paid')
