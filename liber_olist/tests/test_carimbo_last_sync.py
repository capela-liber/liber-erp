# -*- coding: utf-8 -*-
"""Nenhum carimbo de relógio pode derrubar a rodada que o grava.

Em 08/09/2026 o cron "Olist: pull NFe XMLs" falhou quatro vezes seguidas no
prod, e o Odoo avisou que ia desativá-lo. A causa não estava na API: todas as
rotinas escrevem na MESMA linha de `olist_account`, e o push de estoque a
reescreve a cada livro. Quem grava o próprio carimbo no fim de uma transação
longa colide, e o Postgres recusa com `could not serialize access due to
concurrent update`.

Em 10/09 o MESMO erro voltou por outro campo, `last_orders_pull`, derrubando
"Olist: ler pedidos". Era defeito de classe e eu tinha consertado só uma
instância — por isso o teste abaixo varre a lista inteira de carimbos.
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

    def test_todo_carimbo_grava_o_relogio(self):
        """Varre a lista inteira: foi consertar um só que deixou o furo."""
        for campo in self.env['olist.account'].CARIMBOS:
            self.account.write({campo: False})
            self.account._carimba_relogio(campo)
            self.assertTrue(self.account[campo],
                            "o carimbo %s não gravou" % campo)

    def test_carimbo_desconhecido_e_recusado(self):
        """Nome errado é erro de programação, e erro de programação grita."""
        with self.assertRaises(ValueError):
            self.account._carimba_relogio('last_coisa_nenhuma')

    def _fora_do_teste(self):
        """Força o caminho de produção: cursor próprio em vez de escrita direta."""
        return patch.dict(tools.config.options, {'test_enable': False})

    def test_o_carimbo_usa_um_cursor_proprio_em_producao(self):
        """É o cursor curto que impede a linha de ficar presa meio minuto."""
        with self._fora_do_teste(), \
             patch('odoo.addons.liber_olist.models.olist_account.modules'
                   '.module.current_test', None), \
             patch.object(type(self.env.registry), 'cursor') as cursor:
            self.account._carimba_relogio('last_sync')
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
            self.assertTrue(self.account._carimba_relogio('last_sync'))
