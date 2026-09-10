# -*- coding: utf-8 -*-
"""Um plano de contas pontilhado, montado à mão.

Não se usa o demo data do core: ele traz um plano de dois dígitos, que é
exatamente o caso em que a barra lateral antiga já funcionava. O que se quer
provar é o plano da casa -- `1.1.1` -- em que o segundo caractere é o ponto.

As rubricas do teste começam em `7` e `8` de propósito: assim elas não
encostam nas rubricas reais do banco onde a suíte roda (o plano da casa vai
de `1` a `3`), e nada precisa ser apagado para o fixture caber.
"""
from odoo.tests import TransactionCase


class AccountGroupPanelCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Reaproveita a empresa do banco: criar res.company com o `account`
        # instalado quebra em NOT NULL (fiscalyear_last_day).
        cls.company = cls.env.company
        cls.root_company = cls.company.root_id

        def group(prefix, name):
            return cls.env['account.group'].create({
                'name': name,
                'code_prefix_start': prefix,
                'code_prefix_end': prefix,
                'company_id': cls.root_company.id,
            })

        cls.g_ativo = group('7', 'Ativo do Tour')
        cls.g_circulante = group('7.1', 'Ativo Circulante do Tour')
        cls.g_caixa = group('7.1.1', 'Caixa e Equivalentes do Tour')
        cls.g_receber = group('7.1.2', 'Contas a Receber do Tour')
        cls.g_resultado = group('8', 'Resultado do Tour')
        cls.g_receita = group('8.1', 'Receita do Tour')

        def account(code, name, account_type):
            return cls.env['account.account'].create({
                'code': code,
                'name': name,
                'account_type': account_type,
                'company_ids': [(6, 0, [cls.company.id])],
            })

        cls.acc_banco = account('7.1.1.001', 'Banco do Tour', 'asset_cash')
        cls.acc_caixa = account('7.1.1.002', 'Caixa Pequeno do Tour', 'asset_cash')
        cls.acc_clientes = account('7.1.2.001', 'Clientes do Tour', 'asset_receivable')
        # Cai em `7.1` e não mais fundo: não há rubrica `7.1.9`.
        cls.acc_orfa_rasa = account('7.1.9.001', 'Outros Créditos do Tour', 'asset_current')
        # Não cai em rubrica nenhuma: não há `9`.
        cls.acc_sem_rubrica = account('9.9.9.001', 'Fora do Plano do Tour', 'asset_current')
        cls.acc_venda = account('8.1.1.001', 'Venda de Livros do Tour', 'income')

        cls.accounts = (
            cls.acc_banco | cls.acc_caixa | cls.acc_clientes
            | cls.acc_orfa_rasa | cls.acc_sem_rubrica | cls.acc_venda
        )
