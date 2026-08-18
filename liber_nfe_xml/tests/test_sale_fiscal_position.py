# -*- coding: utf-8 -*-
"""Onde mora o padrão fiscal da VENDA.

A consignação declara as posições dela no `liber_soc_fiscal_br`, mas nem toda
instalação tem o SOC — e sem ele não havia lugar nenhum para dizer qual é a
posição de uma venda comum. O campo passou a morar aqui, na raiz da família
fiscal (Olist, Focus, SOC e influencers dependem deste módulo), e o que se
pinta aqui é justamente isso: que ele existe SEM o SOC no caminho.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSaleFiscalPosition(TransactionCase):
    def test_a_empresa_tem_onde_declarar_a_venda(self):
        posicao = self.env['account.fiscal.position'].create({
            'name': "(A) Venda de mercadoria adquirida de terceiros",
            'company_id': self.env.company.id})

        self.env.company.sale_fiscal_position_id = posicao

        self.assertEqual(self.env.company.sale_fiscal_position_id, posicao)

    def test_o_campo_chega_as_definicoes(self):
        """Campo que não aparece em Definições é campo que ninguém preenche —
        foi assim que as posições da consignação passaram meses em branco."""
        settings = self.env['res.config.settings']

        self.assertIn('sale_fiscal_position_id', settings._fields,
                      "o padrão da venda tem de ser configurável pela tela")

    def test_e_por_empresa_nao_uma_chave_global(self):
        """`account.fiscal.position` carrega company_id: um id só valeria numa
        empresa, e a casa tem seis. O campo é da empresa, e o related das
        Definições segue a empresa ativa."""
        campo = self.env['res.company']._fields['sale_fiscal_position_id']
        relacionado = self.env['res.config.settings']._fields[
            'sale_fiscal_position_id']

        self.assertEqual(campo.comodel_name, 'account.fiscal.position')
        self.assertEqual(relacionado.related,
                         'company_id.sale_fiscal_position_id')
