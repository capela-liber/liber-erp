# -*- coding: utf-8 -*-
"""A empresa dos testes, pronta para ter caixa de feira.

Desde 30/10/2026 o caixa não nasce sem a configuração "Caixas de feira" --
conta do dinheiro, sobra e falta; desde 03/11/2026, também transitória, a
receber do PDV e receita. Os testes criam as contas que faltam em vez de
procurar no plano: o banco de teste não tem o plano da casa.
"""


def configurar_caixas_de_feira(env, company):
    """Preenche só o que falta, e devolve a empresa."""
    if not company._fair_register_missing():
        return company
    Conta = env['account.account']

    def conta(codigo, nome, tipo):
        return Conta.create({
            'code': codigo, 'name': nome, 'account_type': tipo,
            'company_ids': [(6, 0, [company.id])]})

    vals = {}
    if not company.fair_cash_account_id:
        vals['fair_cash_account_id'] = conta(
            'FEIRA01', 'Caixa: Feiras', 'asset_cash').id
    if not company.default_cash_difference_income_account_id:
        vals['default_cash_difference_income_account_id'] = conta(
            'FEIRA02', 'Sobra de caixa', 'income_other').id
    if not company.default_cash_difference_expense_account_id:
        vals['default_cash_difference_expense_account_id'] = conta(
            'FEIRA03', 'Falta de caixa', 'expense').id
    if not company.account_journal_suspense_account_id:
        vals['account_journal_suspense_account_id'] = conta(
            'FEIRA04', 'Trânsito', 'asset_current').id
    if not company.account_default_pos_receivable_account_id:
        vals['account_default_pos_receivable_account_id'] = Conta.create({
            'code': 'FEIRA05', 'name': 'A receber do PDV',
            'account_type': 'asset_receivable', 'reconcile': True,
            'company_ids': [(6, 0, [company.id])]}).id
    if not company.fair_income_account_id:
        vals['fair_income_account_id'] = conta(
            'FEIRA06', 'Vendas em feira', 'income').id
    company.write(vals)
    return company
