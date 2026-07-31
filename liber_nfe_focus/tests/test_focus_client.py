# -*- coding: utf-8 -*-
"""Testes do cliente HTTP, com um `requests` falso: nada sai para a rede."""

import json

from odoo.tests import TransactionCase, tagged

from ..models.focus_client import (
    BASE_URLS, FocusAuthError, FocusClient, FocusError, FocusNotFound,
    FocusValidationError,
)


class FakeResponse(object):
    def __init__(self, status_code, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.content = (text or '').encode('utf-8')

    def json(self):
        if self._payload is None:
            raise ValueError('sem JSON')
        return self._payload


class FakeSession(object):
    """Grava a chamada e devolve o que o teste mandar."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def request(self, method, url, **kwargs):
        self.chamadas.append({'method': method, 'url': url, **kwargs})
        return self.respostas.pop(0) if self.respostas else FakeResponse(200, {})


@tagged('post_install', '-at_install', 'focus_nfe')
class TestFocusClient(TransactionCase):

    def _client(self, *respostas):
        sessao = FakeSession(*respostas)
        return FocusClient('tok-123', ambiente='homologacao', session=sessao), sessao

    # -- caminho feliz -------------------------------------------------
    def test_emitir_manda_ref_na_query_e_json_no_corpo(self):
        client, sessao = self._client(
            FakeResponse(202, {'status': 'processando_autorizacao'}))

        resposta = client.emitir_nfe('EDLAB-1-42', {'natureza_operacao': 'Venda'})

        chamada = sessao.chamadas[0]
        self.assertEqual(chamada['method'], 'POST')
        self.assertEqual(chamada['url'],
                         BASE_URLS['homologacao'] + '/v2/nfe')
        self.assertEqual(chamada['params'], {'ref': 'EDLAB-1-42'})
        self.assertEqual(json.loads(chamada['data'].decode('utf-8')),
                         {'natureza_operacao': 'Venda'})
        self.assertEqual(resposta['status'], 'processando_autorizacao')

    def test_autenticacao_e_token_com_senha_vazia(self):
        """`Basic base64("TOKEN:")`. Mandar o token como senha dá 401."""
        client, sessao = self._client(FakeResponse(200, {}))

        client.consultar_nfe('EDLAB-1-42')

        self.assertEqual(sessao.chamadas[0]['auth'], ('tok-123', ''))

    def test_consultar_pede_a_resposta_completa(self):
        client, sessao = self._client(FakeResponse(200, {'status': 'autorizado'}))

        client.consultar_nfe('EDLAB-1-42')

        self.assertEqual(sessao.chamadas[0]['method'], 'GET')
        self.assertTrue(sessao.chamadas[0]['url'].endswith('/v2/nfe/EDLAB-1-42'))
        self.assertEqual(sessao.chamadas[0]['params'], {'completa': 1})

    def test_homologacao_e_producao_batem_em_hosts_diferentes(self):
        homolog, sessao_h = self._client(FakeResponse(200, {}))
        homolog.consultar_nfe('X')
        producao = FocusClient('tok', ambiente='producao', session=FakeSession(
            FakeResponse(200, {})))
        producao.consultar_nfe('X')

        self.assertIn('homologacao.focusnfe.com.br', sessao_h.chamadas[0]['url'])
        self.assertIn('api.focusnfe.com.br',
                      producao.session.chamadas[0]['url'])

    def test_baixar_prefixa_o_caminho_relativo_com_a_base(self):
        client, sessao = self._client(FakeResponse(200, text='<nfeProc/>'))

        conteudo = client.baixar('/arquivos/123/nfe.xml')

        self.assertEqual(conteudo, b'<nfeProc/>')
        self.assertEqual(sessao.chamadas[0]['url'],
                         BASE_URLS['homologacao'] + '/arquivos/123/nfe.xml')

    def test_teste_de_conexao_em_homologacao_nao_usa_empresas(self):
        """`/v2/empresas` só existe em produção; em homologação ele dá 404 e
        faria uma conexão saudável parecer quebrada. Lá o probe é uma consulta
        a uma referência inexistente, e o 404 dela é o sinal de sucesso."""
        client, sessao = self._client(FakeResponse(404, {
            'codigo': 'nao_encontrado', 'mensagem': 'Nota fiscal não encontrada'}))

        self.assertEqual(client.testar_conexao(), [])
        self.assertIn('/v2/nfe/', sessao.chamadas[0]['url'])
        self.assertNotIn('/v2/empresas', sessao.chamadas[0]['url'])

    def test_teste_de_conexao_em_producao_lista_empresas(self):
        producao = FocusClient('tok', ambiente='producao', session=FakeSession(
            FakeResponse(200, [{'id': 1}, {'id': 2}])))

        self.assertEqual(len(producao.testar_conexao()), 2)

    def test_token_invalido_reprova_o_teste_de_conexao(self):
        """O 404 do probe é sucesso, mas o 401 continua sendo falha."""
        client, _s = self._client(FakeResponse(401, {'mensagem': 'token inválido'}))

        with self.assertRaises(FocusAuthError):
            client.testar_conexao()

    # -- casos de erro -------------------------------------------------
    def test_422_vira_erro_de_validacao_com_a_mensagem_da_focus(self):
        client, _s = self._client(FakeResponse(422, {
            'codigo': 'nfe_nao_autorizada',
            'mensagem': 'Rejeicao: CNPJ do destinatario invalido',
        }))

        with self.assertRaises(FocusValidationError) as ctx:
            client.emitir_nfe('EDLAB-1-42', {})

        self.assertIn('CNPJ do destinatario invalido', ctx.exception.message)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.payload['codigo'], 'nfe_nao_autorizada')

    def test_lista_de_erros_vira_uma_frase_so(self):
        client, _s = self._client(FakeResponse(400, {'erros': [
            {'campo': 'cnpj_emitente', 'mensagem': 'não pode ficar em branco'},
            {'campo': 'items', 'mensagem': 'deve ter ao menos um item'},
        ]}))

        with self.assertRaises(FocusValidationError) as ctx:
            client.emitir_nfe('EDLAB-1-42', {})

        self.assertIn('cnpj_emitente', ctx.exception.message)
        self.assertIn('items', ctx.exception.message)

    def test_403_diz_que_o_token_pode_ser_do_outro_ambiente(self):
        client, _s = self._client(FakeResponse(403, {'mensagem': 'acesso negado'}))

        with self.assertRaises(FocusAuthError) as ctx:
            client.consultar_nfe('EDLAB-1-42')

        self.assertIn('homologacao', ctx.exception.message)

    def test_404_e_referencia_inexistente(self):
        client, _s = self._client(FakeResponse(404, {'mensagem': 'não encontrado'}))

        with self.assertRaises(FocusNotFound):
            client.consultar_nfe('EDLAB-1-999')

    def test_resposta_sem_json_nao_quebra_o_parser(self):
        client, _s = self._client(FakeResponse(500, None, text='Bad Gateway'))

        with self.assertRaises(FocusError) as ctx:
            client.consultar_nfe('EDLAB-1-42')

        self.assertIn('Bad Gateway', ctx.exception.message)

    def test_cliente_sem_token_nao_chega_a_ser_construido(self):
        with self.assertRaises(FocusAuthError):
            FocusClient('', ambiente='homologacao')

    def test_ambiente_desconhecido_e_recusado(self):
        with self.assertRaises(FocusError):
            FocusClient('tok', ambiente='producao_de_verdade')

    def test_emitir_sem_referencia_e_recusado_antes_da_rede(self):
        client, sessao = self._client()

        with self.assertRaises(FocusError):
            client.emitir_nfe('', {})

        self.assertEqual(sessao.chamadas, [])

    def test_justificativa_curta_nao_gasta_chamada(self):
        """A SEFAZ exige de 15 a 255 caracteres; checar aqui evita a viagem."""
        client, sessao = self._client()

        with self.assertRaises(FocusValidationError):
            client.cancelar_nfe('EDLAB-1-42', 'errei')

        self.assertEqual(sessao.chamadas, [])

    def test_cancelar_manda_a_justificativa_no_corpo(self):
        client, sessao = self._client(FakeResponse(200, {'status': 'cancelado'}))

        client.cancelar_nfe('EDLAB-1-42', 'Pedido cancelado pelo cliente')

        chamada = sessao.chamadas[0]
        self.assertEqual(chamada['method'], 'DELETE')
        self.assertEqual(json.loads(chamada['data'].decode('utf-8')),
                         {'justificativa': 'Pedido cancelado pelo cliente'})
