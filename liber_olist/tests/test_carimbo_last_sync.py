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

    def test_o_push_nao_usa_cursor_proprio(self):
        """O push é DONO da linha: cursor à parte derrubaria a própria rodada.

        Ele reescreve o `stock_push_cursor` a cada livro e o zera no fim.
        Quando o carimbo passou a commitar num cursor separado, o zeramento foi
        recusado com `could not serialize access` — 11/09/2026, 02:46, o
        conserto de véspera mordendo a si mesmo. Este teste prende a exceção à
        regra: quem já é dono da linha grava direto.
        """
        import inspect
        from odoo.addons.liber_olist.models import olist_account
        fonte = inspect.getsource(olist_account.OlistAccount._push_all_stock)
        self.assertIn("self.last_stock_push = fields.Datetime.now()", fonte,
                      "o push voltou a carimbar por cursor próprio")
        self.assertNotIn("_carimba_relogio('last_stock_push')", fonte)
