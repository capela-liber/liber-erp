# -*- coding: utf-8 -*-
"""A empresa dos testes, pronta para ter caixa de feira.

Desde 30/10/2026 o caixa não nasce sem a configuração "Caixas de feira" --
conta do dinheiro, sobra e falta. Os testes criam as três contas em vez de
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
    company.write(vals)
    return company
