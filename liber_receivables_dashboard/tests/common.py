# -*- coding: utf-8 -*-
"""O que os testes deste módulo semeiam: uma carteira pequena e conhecida.

Um cliente de verdade (tem fatura emitida) com três faturas em três faixas e
um crédito solto; e um "fornecedor" que nunca recebeu fatura mas tem saldo
parado na conta a receber -- é ele que prova que a carteira não absorve o
que não é dela.
"""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase


class CarteiraDeTeste(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.conta = cls.env['account.account'].search([
            ('account_type', '=', 'asset_receivable'),
            ('company_ids', 'in', cls.company.id)], limit=1)
        cls.diario = cls.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', cls.company.id)], limit=1)
        cls.receita = cls.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_ids', 'in', cls.company.id)], limit=1)
        if not (cls.conta and cls.diario and cls.receita):
            cls.skipTest(cls, 'a empresa deste banco não tem o plano de '
                              'contas mínimo para encenar a carteira')
        cls.cliente = cls.env['res.partner'].create({'name': 'Livraria da Carteira'})
        cls.fornecedor = cls.env['res.partner'].create({'name': 'Gráfica no Razão Errado'})
        cls.hoje = fields.Date.context_today(cls.env.user)

    # ---------------------------------------------------------------- semeadura
    def _fatura(self, dias, valor, parceiro=None):
        """Uma fatura de cliente lançada, vencendo em `dias` (negativo = já
        venceu)."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': (parceiro or self.cliente).id,
            'company_id': self.company.id,
            'journal_id': self.diario.id,
            'invoice_date': self.hoje,
            'invoice_date_due': self.hoje + timedelta(days=dias),
            'invoice_line_ids': [(0, 0, {
                'name': 'livro', 'quantity': 1, 'price_unit': valor,
                'account_id': self.receita.id, 'tax_ids': [(5, 0, 0)]})],
        })
        move.action_post()
        return move

    def _lancamento(self, parceiro, debito=0.0, credito=0.0, dias=0):
        """Uma perna solta na conta a receber, contra a receita: é o
        pagamento sem fatura (crédito) ou o saldo parado (débito)."""
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.diario.id,
            'company_id': self.company.id, 'date': self.hoje,
            'line_ids': [
                (0, 0, {'account_id': self.conta.id, 'partner_id': parceiro.id,
                        'date_maturity': self.hoje + timedelta(days=dias),
                        'debit': debito, 'credit': credito}),
                (0, 0, {'account_id': self.receita.id, 'partner_id': parceiro.id,
                        'debit': credito, 'credit': debito}),
            ],
        })
        move.action_post()
        return move

    def _semear(self):
        self._fatura(10, 100.0)        # a vencer
        self._fatura(-15, 200.0)       # 1-30
        self._fatura(-400, 300.0)      # > 120
        self._lancamento(self.cliente, credito=50.0)      # crédito solto
        self._lancamento(self.fornecedor, debito=500.0)   # fora do razão
        self.env.flush_all()

    # ------------------------------------------------------------------ leitura
    def _soma(self, dominio, campo='amount_total', model='liber.aged.receivable'):
        """O mesmo `_read_group` que a planilha manda o servidor fazer,
        restrito aos parceiros do teste."""
        recorte = [('partner_id', 'in', (self.cliente | self.fornecedor).ids)]
        [(total,)] = self.env[model]._read_group(
            list(dominio) + recorte, aggregates=[campo + ':sum'])
        return total or 0.0
