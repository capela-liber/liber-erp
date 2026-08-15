# -*- coding: utf-8 -*-
"""O canal na operação de consignação (o CO).

A tela de operações é a mais usada da consignação e, até 08/08/2026, era a
única que não sabia dizer de que canal era cada remessa -- a prateleira sabia,
a cobertura sabia, a ruptura sabia, a campanha sabia. Sem o campo GRAVADO não
há agrupar: o Odoo não agrupa lista por campo que não está armazenado.

A ordem de leitura é a doutrina da casa: na consignação o CONTRATO manda, e a
ficha do cliente é o padrão de onde o contrato nasce.
"""
from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCanalDaOperacao(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.livrarias = cls.env['crm.team'].create({'name': 'Livrarias de Teste'})
        cls.distribuidoras = cls.env['crm.team'].create({'name': 'Distribuidoras de Teste'})
        cls.product = cls.env['product.product'].create({
            'name': 'Livro de Teste', 'type': 'consu',
            'is_storable': True, 'list_price': 40.0})
        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria da Operação', 'is_company': True,
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

    def _operacao(self, kind='shipment', qty=5):
        return self.env['consignment.move'].create({
            'partner_id': self.partner.id,
            'move_kind': kind,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': qty,
            })],
        })

    def test_canal_vem_do_contrato(self):
        self._com_canal_na_ficha(self.livrarias)
        self._contrato(canal=self.distribuidoras)
        self.assertEqual(self._operacao().team_id, self.distribuidoras,
                         "na consignação o contrato manda")

    def test_sem_contrato_o_canal_vem_da_ficha(self):
        self._com_canal_na_ficha(self.livrarias)
        self.assertEqual(self._operacao().team_id, self.livrarias)

    def test_sem_canal_em_lugar_nenhum_fica_vazio(self):
        """Nunca chuta: vazio quer dizer 'ninguém definiu'."""
        if 'team_id' in self.env['res.partner']._fields:
            self.partner.with_company(self.company).team_id = False
        self.assertFalse(self._operacao().team_id)

    def test_carimbo_nao_se_reescreve(self):
        """Uma remessa de ontem continua sendo do canal em que foi feita.

        Se o canal fosse lido do cliente a cada leitura, corrigir uma ficha
        reescreveria a história -- e o número que já foi apurado mudaria
        sozinho.
        """
        self._com_canal_na_ficha(self.livrarias)
        operacao = self._operacao()
        self.assertEqual(operacao.team_id, self.livrarias)

        self.partner.with_company(self.company).team_id = self.distribuidoras
        operacao.invalidate_recordset(['team_id'])
        self.assertEqual(operacao.team_id, self.livrarias,
                         "o carimbo é do dia da operação, não de hoje")

    def test_da_para_agrupar_por_canal(self):
        """O ponto de existir o campo: a tela agrupa.

        `_read_group` sobre campo não armazenado explode -- é por isso que o
        canal aqui é carimbo e não `related` de passagem.
        """
        self._com_canal_na_ficha(self.livrarias)
        operacao = self._operacao()
        grupos = self.env['consignment.move']._read_group(
            [('id', '=', operacao.id)], ['team_id'], ['__count'])
        self.assertEqual(grupos[0][0], self.livrarias)
        self.assertEqual(grupos[0][1], 1)

    def test_a_busca_oferece_agrupar_por_canal(self):
        arch = self.env['consignment.move'].get_view(
            view_id=self.env.ref('liber_soc_moves.view_consignment_move_search').id,
            view_type='search')['arch']
        self.assertIn('g_team', arch)
