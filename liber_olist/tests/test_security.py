# -*- coding: utf-8 -*-
"""Multiempresa: o Olist de um selo não é assunto do outro.

Sem as regras de registro, qualquer usuário interno via as contas, espelhos e
pedidos de TODAS as empresas — descoberto testando com gente de verdade em
18/08/2026. As empresas são REAPROVEITADAS do banco (criar res.company quebra
com o account instalado: NOT NULL de fiscalyear_last_day).
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOlistMultiempresa(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        empresas = cls.env['res.company'].search([], order='id')
        if len(empresas) < 2:
            cls.skipTest(cls, "só há uma empresa neste banco")
        cls.empresa_a, cls.empresa_b = empresas[0], empresas[1]

        cls.env['olist.account'].search([]).write({'active': False})
        cls.conta_a = cls.env['olist.account'].create({
            'name': "Conta A", 'company_id': cls.empresa_a.id,
            'token': "TOKEN-A", 'read_only': True})
        cls.conta_b = cls.env['olist.account'].create({
            'name': "Conta B", 'company_id': cls.empresa_b.id,
            'token': "TOKEN-B", 'read_only': True})

        cls.pedido_b = cls.env['olist.order'].create({
            'account_id': cls.conta_b.id, 'olist_id': 'SEC-B-1',
            'numero': 'B-1', 'situacao': 'Entregue',
            'line_ids': [(0, 0, {'codigo': '9780000000001',
                                 'descricao': "Livro da B",
                                 'quantidade': 1, 'valor_unitario': 10.0})]})
        cls.espelho_b = cls.env['olist.product'].create({
            'account_id': cls.conta_b.id, 'olist_id': 'SEC-B-P1',
            'codigo': '9780000000001', 'name': "Livro da B"})
        cls.canal_b = cls.env['olist.channel'].create({
            'account_id': cls.conta_b.id, 'name': "Canal da B"})

        # Usuário comum, SÓ da empresa A.
        cls.usuario_a = cls.env['res.users'].create({
            'name': "Operador da A", 'login': "operador.a@teste",
            'company_id': cls.empresa_a.id,
            'company_ids': [(6, 0, [cls.empresa_a.id])],
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])]})

    def _como_a(self, modelo):
        return self.env[modelo].with_user(self.usuario_a).with_context(
            allowed_company_ids=[self.empresa_a.id])

    def test_a_empresa_a_nao_ve_o_olist_da_b(self):
        """Caminho feliz da regra: a busca de A devolve só o que é de A."""
        self.assertFalse(self._como_a('olist.account').search(
            [('id', '=', self.conta_b.id)]))
        self.assertFalse(self._como_a('olist.order').search(
            [('id', '=', self.pedido_b.id)]))
        self.assertFalse(self._como_a('olist.order.line').search(
            [('order_id', '=', self.pedido_b.id)]))
        self.assertFalse(self._como_a('olist.product').search(
            [('id', '=', self.espelho_b.id)]))
        self.assertFalse(self._como_a('olist.channel').search(
            [('id', '=', self.canal_b.id)]))

    def test_a_empresa_a_ve_o_proprio_olist(self):
        """A regra restringe, não esconde tudo: a conta da própria empresa
        continua visível."""
        self.assertTrue(self._como_a('olist.account').search(
            [('id', '=', self.conta_a.id)]))

    def test_ler_o_registro_da_outra_estoura_e_nao_vaza(self):
        """Caso de erro: acesso direto por id (URL adivinhada) não devolve
        dado — levanta o erro de acesso do Odoo."""
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            self._como_a('olist.order').browse(self.pedido_b.id).read(['numero'])
