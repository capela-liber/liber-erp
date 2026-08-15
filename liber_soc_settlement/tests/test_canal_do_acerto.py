# -*- coding: utf-8 -*-
"""O canal no acerto -- no documento, não só na linha.

A LINHA do acerto já trazia o canal (`related` do contrato). O documento, não:
a pergunta que o comercial faz primeiro -- quanto acertou cada canal no mês --
não tinha como ser respondida na tela de acertos, porque não se agrupa lista
por campo que não está armazenado.

E é carimbo, não `related`: o acerto é apuração fechada. Se o canal fosse lido
do cliente a cada leitura, corrigir uma ficha mudaria o canal de um número já
apurado.
"""
from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCanalDoAcerto(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.livrarias = cls.env['crm.team'].create({'name': 'Livrarias de Teste'})
        cls.distribuidoras = cls.env['crm.team'].create({'name': 'Distribuidoras de Teste'})
        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria do Acerto por Canal', 'is_company': True,
            'allow_consignment': True})

    def _com_canal_na_ficha(self, canal):
        if 'team_id' not in self.env['res.partner']._fields:
            self.skipTest("sem `liber_partner_commercial`: a ficha não tem canal")
        self.partner.with_company(self.company).team_id = canal

    def _contrato(self, canal=None):
        contrato = self.env['consignment.agreement'].create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'date_start': fields.Date.today(),
        })
        if canal is not None:
            contrato.team_id = canal
        contrato.action_activate()
        return contrato

    def _acerto(self):
        return self.env['consignment.settlement'].create({
            'partner_id': self.partner.id, 'company_id': self.company.id})

    def test_canal_vem_do_contrato(self):
        self._com_canal_na_ficha(self.livrarias)
        self._contrato(canal=self.distribuidoras)
        self.assertEqual(self._acerto().team_id, self.distribuidoras)

    def test_sem_contrato_o_canal_vem_da_ficha(self):
        self._com_canal_na_ficha(self.livrarias)
        self.assertEqual(self._acerto().team_id, self.livrarias)

    def test_carimbo_nao_se_reescreve(self):
        self._com_canal_na_ficha(self.livrarias)
        acerto = self._acerto()
        # Ler antes de mexer não é firula: enquanto o compute está na fila, o
        # valor ainda não é carimbo -- ele só congela quando é gravado. Na tela
        # isso acontece sozinho ao salvar; aqui é preciso pedir.
        self.assertEqual(acerto.team_id, self.livrarias)

        self.partner.with_company(self.company).team_id = self.distribuidoras
        acerto.invalidate_recordset(['team_id'])
        self.assertEqual(acerto.team_id, self.livrarias,
                         "apuração fechada não muda de canal depois")

    def test_da_para_agrupar_por_canal(self):
        self._com_canal_na_ficha(self.livrarias)
        acerto = self._acerto()
        grupos = self.env['consignment.settlement']._read_group(
            [('id', '=', acerto.id)], ['team_id'], ['__count'])
        self.assertEqual(grupos[0][0], self.livrarias)

    def test_a_busca_oferece_agrupar_por_canal(self):
        arch = self.env['consignment.settlement'].get_view(
            view_id=self.env.ref(
                'liber_soc_settlement.view_consignment_settlement_search').id,
            view_type='search')['arch']
        self.assertIn('g_team', arch)
