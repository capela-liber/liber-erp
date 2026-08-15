# -*- coding: utf-8 -*-
"""O canal do contrato nasce do cliente -- e a exceção, posta à mão, sobrevive.

Antes de 08/08/2026 o campo tinha `default=_get_default_team_id()`, a heurística
do Odoo, que olha as equipes do VENDEDOR. Ela não tem como acertar o canal de um
cliente: numa medição no `merge_02`, 77 dos 262 contratos divergiam da ficha, e
um deles dizia "Sales", a equipe de fábrica. O que se testa aqui é que o
contrato passou a herdar da ficha, e que herdar não virou apagar.
"""
from odoo.tests.common import TransactionCase, tagged


# `post_install` pelo mesmo motivo dos outros: o teste cria `crm.team`, e num
# banco com o `crm` instalado a coluna `alias_id` já é NOT NULL enquanto o mixin
# do alias ainda não entrou no registro.
@tagged('post_install', '-at_install')
class TestCanalDoContrato(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.empresa = cls.env['res.company'].search([], order='id', limit=1)
        cls.livrarias = cls.env['crm.team'].create({'name': 'Livrarias de Teste'})
        cls.distribuidoras = cls.env['crm.team'].create({'name': 'Distribuidoras de Teste'})
        cls.cliente = cls.env['res.partner'].create({
            'name': 'Livraria com Canal', 'is_company': True,
            'allow_consignment': True})

    def _contrato(self, **extra):
        valores = {'partner_id': self.cliente.id, 'company_id': self.empresa.id}
        valores.update(extra)
        return self.env['consignment.agreement'].create(valores)

    def _com_canal(self, canal):
        """Grava o canal na ficha, na empresa do teste (o campo é por empresa)."""
        if 'team_id' not in self.env['res.partner']._fields:
            self.skipTest("sem `liber_partner_commercial`: a ficha não tem canal")
        self.cliente.with_company(self.empresa).team_id = canal

    def test_nasce_do_canal_do_cliente(self):
        self._com_canal(self.livrarias)
        self.assertEqual(self._contrato().team_id, self.livrarias)

    def test_cliente_sem_canal_deixa_o_contrato_vazio(self):
        """Vazio é melhor do que chute.

        O default antigo preenchia com a primeira equipe que a heurística
        achasse -- ruído com cara de dado.
        """
        if 'team_id' in self.env['res.partner']._fields:
            self.cliente.with_company(self.empresa).team_id = False
        self.assertFalse(self._contrato().team_id)

    def test_excecao_posta_a_mao_fica(self):
        """Escrito à mão, o valor fica -- enquanto o cliente for o mesmo."""
        self._com_canal(self.livrarias)
        contrato = self._contrato()
        contrato.team_id = self.distribuidoras
        contrato.flush_recordset()
        contrato.invalidate_recordset(['team_id'])
        self.assertEqual(contrato.team_id, self.distribuidoras)

    def test_corrigir_a_ficha_nao_reescreve_o_contrato(self):
        """A diferença entre carimbo e espelho.

        A dependência é `partner_id` (o vínculo), não `partner_id.team_id`.
        Reclassificar um cliente hoje não muda o canal de um contrato feito em
        2024 -- se mudasse, o histórico se reescreveria sozinho.
        """
        self._com_canal(self.livrarias)
        contrato = self._contrato()
        self.assertEqual(contrato.team_id, self.livrarias)

        self.cliente.with_company(self.empresa).team_id = self.distribuidoras
        contrato.invalidate_recordset(['team_id'])
        self.assertEqual(contrato.team_id, self.livrarias)

    def test_trocar_o_cliente_repuxa_o_canal(self):
        """O que o operador espera, e que uma trava minha impedia: mudou o
        cliente, o canal acompanha -- como a lista de preço no pedido."""
        self._com_canal(self.livrarias)
        contrato = self._contrato()
        self.assertEqual(contrato.team_id, self.livrarias)

        outro = self.env['res.partner'].create({
            'name': 'Distribuidora Outra', 'is_company': True,
            'allow_consignment': True})
        outro.with_company(self.empresa).team_id = self.distribuidoras
        contrato.partner_id = outro
        self.assertEqual(contrato.team_id, self.distribuidoras)

    def test_canal_informado_na_criacao_manda(self):
        self._com_canal(self.livrarias)
        contrato = self._contrato(team_id=self.distribuidoras.id)
        self.assertEqual(contrato.team_id, self.distribuidoras)

    def test_filial_herda_o_canal_da_matriz(self):
        """A ficha da filial costuma vir vazia; o acordo comercial é da conta."""
        self._com_canal(self.livrarias)
        filial = self.env['res.partner'].create({
            'name': 'Filial Centro', 'is_company': True,
            'parent_id': self.cliente.id, 'allow_consignment': True})
        contrato = self._contrato(partner_id=filial.id)
        self.assertEqual(contrato.team_id, self.livrarias)

    def test_o_canal_e_por_empresa(self):
        """Duas editoras, dois canais para o mesmo cliente."""
        empresas = self.env['res.company'].search([], order='id', limit=2)
        if len(empresas) < 2:
            self.skipTest("precisa de duas empresas no banco")
        if 'team_id' not in self.env['res.partner']._fields:
            self.skipTest("sem `liber_partner_commercial`")
        self.cliente.with_company(empresas[0]).team_id = self.livrarias
        self.cliente.with_company(empresas[1]).team_id = self.distribuidoras
        self.assertEqual(self._contrato(company_id=empresas[0].id).team_id,
                         self.livrarias)
        self.assertEqual(self._contrato(company_id=empresas[1].id).team_id,
                         self.distribuidoras)
