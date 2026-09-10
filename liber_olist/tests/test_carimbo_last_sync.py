# -*- coding: utf-8 -*-
"""O carimbo do relógio não pode derrubar a leitura de notas.

Em 08/09/2026 o cron "Olist: pull NFe XMLs" falhou quatro vezes seguidas no
prod, e o Odoo avisou que ia desativá-lo. A causa não estava na API: duas
rotinas escrevem na MESMA linha de `olist_account` — o push de estoque grava
`stock_push_cursor` a cada livro, e a leitura de notas grava `last_sync` no
fim de uma transação de trinta segundos. O Postgres recusou a segunda com
`could not serialize access due to concurrent update` e a rodada inteira
morreu por causa de um campo informativo.
"""
from unittest.mock import patch

from odoo import tools
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCarimboLastSync(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Conta do carimbo", 'company_id': cls.env.company.id,
            'token': "TOKEN-C", 'read_only': True,
        })

    def test_o_carimbo_grava_o_relogio(self):
        self.assertFalse(self.account.last_sync)
        self.account._carimba_last_sync()
        self.assertTrue(self.account.last_sync,
                        "a rodada não registrou quando leu as notas")

    def _fora_do_teste(self):
        """Força o caminho de produção: cursor próprio em vez de escrita direta."""
        return patch.dict(tools.config.options, {'test_enable': False})

    def test_o_carimbo_usa_um_cursor_proprio_em_producao(self):
        """É o cursor curto que impede a linha de ficar presa meio minuto."""
        with self._fora_do_teste(), \
             patch('odoo.addons.liber_olist.models.olist_account.modules'
                   '.module.current_test', None), \
             patch.object(type(self.env.registry), 'cursor') as cursor:
            self.account._carimba_last_sync()
        cursor.assert_called_once()

    def test_o_carimbo_que_falha_nao_derruba_a_rodada(self):
        """O caso de erro, que é o motivo de tudo isto existir.

        Se o carimbo colidir de novo, o preço é um `last_sync` desatualizado —
        campo informativo — e nunca a leitura de notas inteira.
        """
        from psycopg2.errors import SerializationFailure
        with self._fora_do_teste(), \
             patch('odoo.addons.liber_olist.models.olist_account.modules'
                   '.module.current_test', None), \
             patch.object(type(self.env.registry), 'cursor',
                          side_effect=SerializationFailure(
                              "could not serialize access")):
            # Não levanta: é este o contrato.
            self.assertTrue(self.account._carimba_last_sync())
