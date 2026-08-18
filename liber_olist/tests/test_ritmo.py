# -*- coding: utf-8 -*-
"""O espaçamento entre chamadas: ritmo sustentado sem penalizar a avulsa.

Medido em 17/08/2026 contra a conta real: a chamada de rede leva **0,41s** e o
cliente devolvia em **2,70s**. Os 2,3s de diferença eram espera nossa — e ela
acontecia DEPOIS da resposta, então ler o detalhe de um pedido só custava o
atraso inteiro sem que ninguém ganhasse nada com isso.

Espaçando pelo relógio (dormir só o que falta desde a última chamada), o ritmo
sustentado continua o mesmo — que é o que a cota exige — e quem clica num
pedido não espera à toa.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_olist.models import olist_client


class _Resposta:
    def read(self):
        return b'{"retorno":{"status":"OK"}}'

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@tagged('post_install', '-at_install')
class TestOlistRitmo(TransactionCase):

    def setUp(self):
        super().setUp()
        olist_client._ultima_chamada = 0.0

    def test_a_single_call_does_not_sleep_afterwards(self):
        """A chamada avulsa sai na velocidade da rede.

        É o caso do dia a dia: alguém abre um pedido e clica em Ler detalhe.
        Fazer essa pessoa esperar 2,2s depois da resposta não protege cota
        nenhuma — não há próxima chamada.
        """
        with patch.object(olist_client.urllib.request, 'urlopen',
                          return_value=_Resposta()), \
             patch.object(olist_client.time, 'sleep') as dormiu:
            olist_client.call('T', 'x.php')
        # o relógio zerado faz a primeira chamada não esperar
        self.assertFalse([c for c in dormiu.call_args_list if c.args[0] > 0],
                         "dormiu sem ter próxima chamada para proteger")

    def test_consecutive_calls_keep_the_spacing(self):
        esperas = []
        with patch.object(olist_client.urllib.request, 'urlopen',
                          return_value=_Resposta()), \
             patch.object(olist_client.time, 'sleep',
                          side_effect=lambda s: esperas.append(s)), \
             patch.object(olist_client.time, 'monotonic',
                          side_effect=[0.0, 0.0, 0.1, 0.1]):
            olist_client.call('T', 'x.php')
            olist_client.call('T', 'x.php')
        # a segunda chamada, colada na primeira, espera quase o intervalo todo
        self.assertTrue(any(e > 2.0 for e in esperas),
                        "duas chamadas seguidas sem espaçamento: a cota estoura")

    def test_a_call_after_a_long_pause_does_not_wait(self):
        # Quem volta depois de pensar não paga pelo intervalo já decorrido.
        with patch.object(olist_client.urllib.request, 'urlopen',
                          return_value=_Resposta()), \
             patch.object(olist_client.time, 'sleep') as dormiu, \
             patch.object(olist_client.time, 'monotonic',
                          side_effect=[100.0, 100.0]):
            olist_client._ultima_chamada = 0.0   # muito tempo atrás
            olist_client.call('T', 'x.php')
        self.assertFalse([c for c in dormiu.call_args_list if c.args[0] > 0])
