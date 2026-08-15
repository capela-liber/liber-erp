# -*- coding: utf-8 -*-
"""Jurídico: quem redige não assina, quem assina não configura.

A régua veio dita pela direção (05/08/2026) e tem três degraus, cada um com
o seu verbo: o Assistente LÊ o app inteiro e REDIGE minutas; o Gerente
ASSINA (valida, cancela, renova); a CONFIGURAÇÃO não é de nenhum dos dois --
é da Direção, exceção consciente à regra "gerente configura a própria área"
que vale nos outros departamentos.

O que este teste segura é a matemática dos implied_ids nos três degraus e,
no degrau de baixo, que "ler tudo" é verdade material: contrato, conta
analítica, relatório de royalty (analytic.line) e fatura (account.move)
abrem em leitura -- e continuam fechados para escrita.
"""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_roles')
class TestJuridico(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        company = cls.env.company

        def _usuario(nome, login, funcao):
            return Users.create({
                'name': nome, 'login': login,
                'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
                'group_ids': [(4, cls.env.ref('liber_roles.%s' % funcao).id)],
            })

        cls.assistente = _usuario('Jurídico Assistente',
                                  'juridico@liber.test',
                                  'group_juridico_assistente')
        cls.gerente = _usuario('Jurídico Gerente',
                               'juridico.gerente@liber.test',
                               'group_juridico_gerente')
        cls.direcao = _usuario('Direção', 'direcao.jur@liber.test',
                               'group_direcao')

        cls.author = cls.env['res.partner'].create({'name': 'Autora Teste'})
        cls.work = cls.env['product.template'].create({'name': 'Obra Teste'})
        cls.contract = cls.env['edlab.contract'].create({
            'company_id': company.id,
            'royalty_line_ids': [(0, 0, {
                'partner_id': cls.author.id,
                'product_id': cls.work.id,
                'tier_ids': [(0, 0, {
                    'qty_from': 0, 'qty_to': 0, 'percentage': 10.0})],
            })],
        })
        cls.env.flush_all()
        cls.env.registry.clear_cache()

    def _tem(self, user, xmlid):
        return user.has_group(xmlid)

    # -- a escada -----------------------------------------------------------

    def test_escada_de_grupos(self):
        """Assistente é user; Gerente é manager; Direção é config (e por
        implicação, tudo). Nenhum degrau vaza para cima."""
        user = 'liber_copyright_contracts.group_contract_user'
        manager = 'liber_copyright_contracts.group_contract_manager'
        config = 'liber_copyright_contracts.group_contract_config'

        self.assertTrue(self._tem(self.assistente, user))
        self.assertFalse(self._tem(self.assistente, manager))

        self.assertTrue(self._tem(self.gerente, manager))
        self.assertFalse(self._tem(self.gerente, config))

        self.assertTrue(self._tem(self.direcao, config))
        self.assertTrue(self._tem(self.direcao, manager))

    # -- assistente: lê tudo, redige, não assina ---------------------------

    def test_assistente_le_o_app_inteiro(self):
        for model in ('edlab.contract', 'account.analytic.account',
                      'account.analytic.line', 'account.move'):
            self.env[model].with_user(self.assistente).search([], limit=1)

    def test_assistente_redige_mas_nao_assina(self):
        Contract = self.env['edlab.contract'].with_user(self.assistente)
        minuta = Contract.create({'company_id': self.env.company.id})
        self.assertEqual(minuta.state, 'draft')
        with self.assertRaises(AccessError):
            minuta.action_validate()

    def test_assistente_nao_escreve_no_analitico(self):
        conta = self.env['account.analytic.account'].search([], limit=1)
        if not conta:
            self.skipTest('base sem conta analítica')
        with self.assertRaises(AccessError):
            conta.with_user(self.assistente).write({'name': 'X'})

    # -- gerente: assina ----------------------------------------------------

    def test_gerente_assina(self):
        contrato = self.contract.with_user(self.gerente)
        contrato.action_validate()
        self.assertEqual(contrato.state, 'valid')
