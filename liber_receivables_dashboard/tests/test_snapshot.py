# -*- coding: utf-8 -*-
"""A foto mensal: o que ela guarda, quando se repete, e o que recusa."""
from datetime import timedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from ..models.receivables_snapshot import (
    CARTEIRA, CAMPO_DA_FAIXA, DOMINIO_CARTEIRA, DOMINIO_CREDITO,
    DOMINIO_FORA_DO_RAZAO, FAIXAS)
from .common import CarteiraDeTeste


@tagged('post_install', '-at_install', 'liber_receivables_dashboard')
class TestReceivablesSnapshot(CarteiraDeTeste):

    def _fotos(self, dia=None):
        return self.env['liber.receivables.snapshot'].search([
            ('company_id', '=', self.company.id),
            ('date', '=', dia or self.hoje)])

    def _valor(self, fotos, faixa):
        [foto] = fotos.filtered(lambda f: f.bracket == faixa)
        return foto.amount

    # ------------------------------------------------------- caminho feliz
    def test_a_foto_guarda_o_que_a_view_diz_hoje(self):
        self._semear()
        self.env['liber.receivables.snapshot']._tirar_foto()
        fotos = self._fotos()
        self.assertEqual(len(fotos), len(FAIXAS), 'uma linha por faixa')
        Aged = self.env['liber.aged.receivable']
        empresa = [('company_id', '=', self.company.id)]
        for faixa in CARTEIRA:
            [(esperado,)] = Aged._read_group(
                DOMINIO_CARTEIRA + empresa,
                aggregates=[CAMPO_DA_FAIXA[faixa] + ':sum'])
            self.assertAlmostEqual(self._valor(fotos, faixa), esperado or 0.0, 2,
                                   'a faixa %s da foto não é a da view' % faixa)
        for dominio, faixa in ((DOMINIO_CREDITO, 'credit'),
                               (DOMINIO_FORA_DO_RAZAO, 'off_ledger')):
            [(esperado,)] = Aged._read_group(dominio + empresa,
                                             aggregates=['amount_total:sum'])
            self.assertAlmostEqual(self._valor(fotos, faixa), esperado or 0.0, 2)
        # E a carteira do teste está lá dentro: 600 nas seis faixas, o
        # crédito de 50 e os 500 do fornecedor nos baldes de fora.
        self.assertGreaterEqual(sum(self._valor(fotos, f) for f in CARTEIRA), 600.0)
        self.assertLessEqual(self._valor(fotos, 'credit'), -50.0)
        self.assertGreaterEqual(self._valor(fotos, 'off_ledger'), 500.0)

    def test_uma_foto_por_mes_a_nova_substitui_a_anterior(self):
        """O gráfico soma por mês: duas fotos no mesmo mês dobrariam a carteira."""
        Foto = self.env['liber.receivables.snapshot']
        Foto._tirar_foto()
        antes = self._valor(self._fotos(), 'current')
        self._fatura(10, 100.0)
        self.env.flush_all()
        Foto._tirar_foto()
        fotos = self._fotos()
        self.assertEqual(len(fotos), len(FAIXAS), 'a segunda foto não pode se somar à primeira')
        self.assertAlmostEqual(self._valor(fotos, 'current'), antes + 100.0, 2)
        # Mesmo com outra data dentro do mesmo mês: só uma sobrevive.
        outro_dia = self.hoje.replace(day=1)
        if outro_dia != self.hoje:
            Foto._tirar_foto(outro_dia)
            self.assertFalse(self._fotos(), 'a foto de hoje devia ter cedido lugar')
            self.assertEqual(len(self._fotos(outro_dia)), len(FAIXAS))

    def test_o_cron_existe_e_chama_a_foto(self):
        cron = self.env.ref('liber_receivables_dashboard.cron_receivables_snapshot')
        self.assertTrue(cron.active)
        self.assertEqual(cron.interval_type, 'months')
        self.assertEqual(cron.model_id.model, 'liber.receivables.snapshot')
        self.assertIn('_cron_tirar_foto', cron.code)
        self.env['liber.receivables.snapshot']._cron_tirar_foto()
        self.assertEqual(len(self._fotos()), len(FAIXAS))

    # ------------------------------------------------------------ arestas
    def test_a_foto_e_de_toda_empresa_inclusive_a_que_esta_zerada(self):
        self.env['liber.receivables.snapshot']._tirar_foto()
        for empresa in self.env['res.company'].sudo().search([]):
            fotos = self.env['liber.receivables.snapshot'].sudo().search([
                ('company_id', '=', empresa.id), ('date', '=', self.hoje)])
            self.assertEqual(len(fotos), len(FAIXAS),
                             'a empresa %s ficou sem foto' % empresa.name)

    def test_cada_editora_ve_so_a_sua_foto(self):
        outras = self.env['res.company'].sudo().search([('id', '!=', self.company.id)])
        if not outras:
            self.skipTest('este banco tem uma empresa só')
        self.env['liber.receivables.snapshot']._tirar_foto()
        de_uma = self.env['res.users'].create({
            'name': 'Financeiro de uma editora', 'login': 'foto_de_uma_editora',
            'company_id': self.company.id, 'company_ids': [(6, 0, [self.company.id])],
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('account.group_account_user').id])],
        })
        vistas = self.env['liber.receivables.snapshot'].with_user(de_uma).search([])
        self.assertTrue(vistas)
        self.assertEqual(vistas.mapped('company_id'), self.company)

    # ------------------------------------------------------------- erros
    def test_foto_do_futuro_e_recusada(self):
        with self.assertRaises(UserError):
            self.env['liber.receivables.snapshot']._tirar_foto(
                self.hoje + timedelta(days=1))

    def test_quem_so_le_a_contabilidade_nao_tira_foto(self):
        leitor = self.env['res.users'].create({
            'name': 'Leitor da contabilidade', 'login': 'leitor_da_foto',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('account.group_account_readonly').id])],
        })
        Foto = self.env['liber.receivables.snapshot'].with_user(leitor)
        Foto.search([])  # ler pode
        with self.assertRaises(AccessError):
            Foto.create({'date': self.hoje, 'company_id': self.company.id,
                         'bracket': 'current', 'amount': 1.0})
