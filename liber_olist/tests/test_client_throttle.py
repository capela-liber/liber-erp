# -*- coding: utf-8 -*-
"""O estrangulamento da API não é erro de rede — e não pode matar a varredura.

Em 13/08/2026 uma leitura completa do catálogo morreu no meio com
`API Bloqueada - Excedido o número de acessos`. O detalhe que engana: isso
chega como **HTTP 200**, com o erro dentro do envelope. Para quem só olha o
código HTTP, é indistinguível de "esse registro não existe" — e foi assim que,
na primeira rodada da Fase 0, 155 notas de 705 sumiram em silêncio.

Quem chama está sempre num laço longo (mil notas, seiscentos saldos). Desistir
no primeiro bloqueio perde a varredura inteira; pior, perde mentindo o motivo.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_olist.models import olist_client

BLOQUEADO = ('{"retorno":{"status":"Erro","codigo_erro":"6","erros":'
             '[{"erro":"API Bloqueada - Excedido o número de acessos a API, '
             'aguarde alguns minutos e tente novamente"}]}}')
OK = '{"retorno":{"status":"OK","produto":{"saldo":7}}}'
ERRO_REAL = ('{"retorno":{"status":"Erro","codigo_erro":"20",'
             '"erros":[{"erro":"Token inválido"}]}}')


@tagged('post_install', '-at_install')
class TestOlistThrottle(TransactionCase):

    def test_throttle_is_retried_not_raised(self):
        respostas = [BLOQUEADO, BLOQUEADO, OK]
        with patch.object(olist_client, 'call', side_effect=respostas), \
             patch.object(olist_client.time, 'sleep') as dormiu:
            payload = olist_client.call_json('T', 'produto.obter.estoque.php')
        self.assertEqual(payload['produto']['saldo'], 7,
                         "desistiu no bloqueio em vez de insistir")
        self.assertTrue(dormiu.called, "insistiu sem esperar — isso é martelar")

    def test_backoff_grows(self):
        with patch.object(olist_client, 'call',
                          side_effect=[BLOQUEADO, BLOQUEADO, OK]), \
             patch.object(olist_client.time, 'sleep') as dormiu:
            olist_client.call_json('T', 'x.php')
        esperas = [c.args[0] for c in dormiu.call_args_list]
        self.assertGreater(esperas[-1], esperas[0],
                           "a espera tem de crescer, senão é martelo lento")

    def test_a_real_error_still_raises_immediately(self):
        # Token inválido não melhora com o tempo: insistir seria esconder.
        with patch.object(olist_client, 'call', return_value=ERRO_REAL):
            with self.assertRaises(olist_client.OlistError):
                olist_client.call_json('T', 'x.php')

    def test_gives_up_eventually_instead_of_looping_forever(self):
        with patch.object(olist_client, 'call', return_value=BLOQUEADO), \
             patch.object(olist_client.time, 'sleep'):
            with self.assertRaises(olist_client.OlistError):
                olist_client.call_json('T', 'x.php', attempts=3)

    def test_spacing_fits_the_floor_plan(self):
        # 30 req/min é o piso da grade de planos, e o teto da nossa conta não é
        # determinável por documentação (NOTES §9.2): o número aqui é empírico.
        self.assertGreaterEqual(olist_client.REQUEST_DELAY, 2.0)
