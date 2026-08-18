# -*- coding: utf-8 -*-
"""Semear o espelho de estoque, e não confundir zero com silêncio.

A janela do cron pergunta "o que mudou desde a última leitura?" — mantém em
dia o que já foi lido e NÃO preenche o que nunca foi. Sem uma semeadura, o
espelho fica com o catálogo inteiro marcando 0,00, indistinguível de "o Olist
está sem estoque": foi o que o dono viu em 18/08/2026, 580 livros zerados que
na verdade nunca tinham sido perguntados.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_olist.models import olist_client


@tagged('post_install', '-at_install')
class TestSemeaduraDeEstoque(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Estoque", 'company_id': cls.env.company.id,
            'token': "TOKEN-E", 'read_only': True})
        cls.linha = cls.env['olist.product'].create({
            'account_id': cls.account.id, 'olist_id': '777',
            'codigo': '9789999999999', 'name': "Livro do Saldo"})

    def test_traco_enquanto_nunca_foi_lido(self):
        self.assertFalse(self.linha.saldo_olist_date)
        self.assertEqual(self.linha.saldo_olist_texto, "—",
                         "sem leitura, a tela não pode mostrar 0,00: é "
                         "ausência de resposta, não saldo zero")

    def test_zero_lido_aparece_como_zero(self):
        """Zero de verdade é informação, e tem de aparecer como número."""
        with patch.object(olist_client, 'get_estoque',
                          return_value={'saldo': '0'}):
            self.linha.action_pull_all_stock()

        self.assertTrue(self.linha.saldo_olist_date)
        self.assertEqual(self.linha.saldo_olist_texto, "0")

    def test_semeadura_le_livro_a_livro(self):
        """O Olist recusa janela maior que 30 dias, então a semeadura é uma
        chamada por livro — e começa pelos que nunca foram lidos."""
        outra = self.env['olist.product'].create({
            'account_id': self.account.id, 'olist_id': '888',
            'codigo': '9788888888888', 'name': "Livro Já Lido",
            'saldo_olist': 3.0, 'saldo_olist_date': '2026-08-01 10:00:00'})
        pedidos = []

        def fake(token, id_produto):
            pedidos.append(id_produto)
            return {'saldo': '12'}

        with patch.object(olist_client, 'get_estoque', fake):
            (self.linha | outra).action_pull_all_stock()

        self.assertEqual(pedidos[0], '777',
                         "quem nunca foi lido vem primeiro: é a linha que "
                         "hoje mente na tela")
        self.assertEqual(self.linha.saldo_olist, 12.0)
        self.assertEqual(self.linha.saldo_olist_texto, "12")

    def test_a_janela_do_cron_continua_incremental(self):
        """A semeadura não pode ter transformado o cron numa varredura.

        A data sai convertida para o fuso do Olist (UTC-3), de propósito: a
        última leitura é gravada em UTC e lá se fala em horário local — meia
        -noite UTC do dia 17 é 21h do dia 16 em Brasília."""
        self.account.last_stock_pull = fields.Datetime.now() - timedelta(days=1)
        capturado = {}

        def fake(token, desde):
            capturado['desde'] = desde
            return []

        with patch.object(olist_client, 'list_atualizacoes_estoque', fake):
            self.account._pull_stock_window()

        pedido = datetime.strptime(capturado['desde'], "%d/%m/%Y %H:%M:%S")
        ontem = datetime.now() - timedelta(days=1)
        self.assertLess(abs((pedido - ontem).total_seconds()), 6 * 3600,
                        "o cron pergunta desde a última leitura (no fuso de "
                        "lá), e não desde o começo dos tempos")

    def test_janela_velha_demais_e_aparada_em_30_dias(self):
        """O Olist recusa mais que 30 dias: cron parado um mês derrubaria a
        rodada inteira se pedisse a janela crua."""
        self.account.last_stock_pull = fields.Datetime.now() - timedelta(days=90)
        capturado = {}

        def fake(token, desde):
            capturado['desde'] = desde
            return []

        with patch.object(olist_client, 'list_atualizacoes_estoque', fake):
            self.account._pull_stock_window()

        pedido = datetime.strptime(capturado['desde'], "%d/%m/%Y %H:%M:%S")
        idade = (datetime.now() - pedido).days
        self.assertLessEqual(idade, 31, "a janela tem de ser aparada em 30 dias")
