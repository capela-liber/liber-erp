# -*- coding: utf-8 -*-
"""Cliente HTTP da API Focus NFe (v2), sem ORM.

Este módulo não importa nada do Odoo de propósito: é a camada que fala com a
Focus e nada mais, para poder ser testada com um `requests` falso, sem banco.

A Focus é REST puro:

    POST   /v2/nfe?ref=REF        emite (assíncrono, responde 202)
    GET    /v2/nfe/REF?completa=1 consulta
    DELETE /v2/nfe/REF            cancela (JSON com justificativa)
    POST   /v2/nfe/REF/carta_correcao

A autenticação é HTTP Basic com o token no lugar do usuário e a senha vazia
(`Authorization: Basic base64("TOKEN:")`) -- o mesmo em homologação e produção,
o que muda é a URL base e o token.

Quem assina o XML e transmite para a SEFAZ é o servidor da Focus: o certificado
A1 fica lá, no cadastro do emitente, nunca do nosso lado.
"""

import json
import logging

import requests

_logger = logging.getLogger(__name__)

# Ambientes. As chaves são os valores do Selection em res.company.
BASE_URLS = {
    'producao': 'https://api.focusnfe.com.br',
    'homologacao': 'https://homologacao.focusnfe.com.br',
}

DEFAULT_TIMEOUT = 60

# Status devolvidos no campo "status" da consulta.
STATUS_PROCESSANDO = 'processando_autorizacao'
STATUS_AUTORIZADO = 'autorizado'
STATUS_CANCELADO = 'cancelado'
STATUS_ERRO = 'erro_autorizacao'
STATUS_DENEGADO = 'denegado'

# Estados em que ainda vale a pena consultar de novo.
PENDING_STATUSES = (STATUS_PROCESSANDO,)

# Referência inexistente, usada só para provar que o token é aceito.
PROBE_REF = '__teste_de_conexao__'


class FocusError(Exception):
    """Qualquer falha vinda da Focus.

    Guarda o corpo devolvido pela API para que a camada Odoo possa mostrá-lo
    ao usuário sem ter que reparsear a resposta.
    """

    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}


class FocusAuthError(FocusError):
    """401/403 -- token errado, ausente, ou de outro ambiente."""


class FocusValidationError(FocusError):
    """400/422 -- a nota foi recusada antes de chegar à SEFAZ.

    É o erro mais comum e o mais útil: a Focus devolve `codigo` e `mensagem`
    dizendo qual campo está faltando ou inválido.
    """


class FocusNotFound(FocusError):
    """404 -- a referência não existe nesse ambiente."""


def _describe(payload):
    """Transforma o corpo de erro da Focus numa frase legível.

    A API responde de três jeitos diferentes conforme o erro:
    `{"codigo": ..., "mensagem": ...}`, `{"erros": [{"campo":..., "mensagem":...}]}`
    ou texto puro. Os três acabam aqui.
    """
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return str(payload)

    erros = payload.get('erros')
    if erros:
        partes = []
        for erro in erros:
            if isinstance(erro, dict):
                campo = erro.get('campo')
                msg = erro.get('mensagem') or erro.get('erro') or ''
                partes.append('%s: %s' % (campo, msg) if campo else msg)
            else:
                partes.append(str(erro))
        return ' | '.join(p for p in partes if p)

    mensagem = payload.get('mensagem') or payload.get('erro') or ''
    codigo = payload.get('codigo')
    if codigo and mensagem:
        return '[%s] %s' % (codigo, mensagem)
    return mensagem or json.dumps(payload, ensure_ascii=False)


class FocusClient(object):
    """Cliente da API Focus NFe.

    :param token: token do emitente (do painel da Focus). O de homologação e o
        de produção são diferentes -- usar o errado devolve 403.
    :param ambiente: 'homologacao' ou 'producao'.
    :param session: injetável nos testes; qualquer objeto com `.request()`.
    """

    def __init__(self, token, ambiente='homologacao', timeout=DEFAULT_TIMEOUT,
                 session=None, verify=True):
        if not token:
            raise FocusAuthError("Token da Focus NFe não configurado.")
        if ambiente not in BASE_URLS:
            raise FocusError("Ambiente desconhecido: %r" % (ambiente,))
        self.token = token
        self.ambiente = ambiente
        self.base_url = BASE_URLS[ambiente]
        self.timeout = timeout
        self.verify = verify
        self.session = session or requests

    # ------------------------------------------------------------------
    # transporte
    # ------------------------------------------------------------------
    def _request(self, method, path, params=None, body=None):
        url = self.base_url + path
        # A senha vazia é obrigatória: `Basic base64("TOKEN:")`. Mandar o token
        # como senha, ou sem os dois pontos, dá 401.
        kwargs = {
            'auth': (self.token, ''),
            'timeout': self.timeout,
            'verify': self.verify,
            'params': params or None,
        }
        if body is not None:
            kwargs['data'] = json.dumps(body, ensure_ascii=False).encode('utf-8')
            kwargs['headers'] = {'Content-Type': 'application/json'}

        _logger.debug("Focus NFe %s %s params=%s", method, url, params)
        try:
            response = self.session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            raise FocusError(
                "Falha de rede ao falar com a Focus NFe: %s" % exc) from exc

        return self._handle(response)

    def _handle(self, response):
        status = response.status_code
        try:
            payload = response.json()
        except ValueError:
            payload = (response.text or '').strip()

        if status in (200, 201, 202):
            return payload if isinstance(payload, (dict, list)) else {}

        detalhe = _describe(payload)
        if status in (401, 403):
            raise FocusAuthError(
                "Focus NFe recusou o token (%s). Confira se o token é o do "
                "ambiente '%s'. %s" % (status, self.ambiente, detalhe),
                status_code=status, payload=payload)
        if status == 404:
            raise FocusNotFound(
                "Referência não encontrada na Focus NFe (404). %s" % detalhe,
                status_code=status, payload=payload)
        if status in (400, 422):
            raise FocusValidationError(
                "Focus NFe recusou a nota (%s). %s" % (status, detalhe),
                status_code=status, payload=payload)
        raise FocusError(
            "Erro inesperado da Focus NFe (%s). %s" % (status, detalhe),
            status_code=status, payload=payload)

    # ------------------------------------------------------------------
    # NFe modelo 55
    # ------------------------------------------------------------------
    def emitir_nfe(self, ref, payload):
        """POST /v2/nfe?ref=REF

        A emissão é assíncrona: a resposta 202 só diz que a nota entrou na
        fila (`status: processando_autorizacao`). A autorização vem depois,
        via `consultar_nfe`.

        `ref` é a nossa chave, não a da Focus: reenviar a mesma ref NÃO emite
        uma segunda nota, devolve a que já existe. É o que protege contra
        duplicidade quando o POST dá timeout.
        """
        if not ref:
            raise FocusError("A NFe precisa de uma referência (ref).")
        return self._request('POST', '/v2/nfe', params={'ref': ref}, body=payload)

    def consultar_nfe(self, ref, completa=True):
        """GET /v2/nfe/REF?completa=1"""
        params = {'completa': 1} if completa else None
        return self._request('GET', '/v2/nfe/%s' % ref, params=params)

    def cancelar_nfe(self, ref, justificativa):
        """DELETE /v2/nfe/REF

        Síncrono: fala com a SEFAZ na hora. A justificativa tem que ter entre
        15 e 255 caracteres -- a SEFAZ rejeita fora disso, então checamos aqui
        para não gastar a viagem.
        """
        texto = (justificativa or '').strip()
        if not 15 <= len(texto) <= 255:
            raise FocusValidationError(
                "A justificativa de cancelamento precisa ter de 15 a 255 "
                "caracteres (tem %d)." % len(texto))
        return self._request('DELETE', '/v2/nfe/%s' % ref,
                             body={'justificativa': texto})

    def carta_correcao(self, ref, correcao):
        """POST /v2/nfe/REF/carta_correcao"""
        texto = (correcao or '').strip()
        if not 15 <= len(texto) <= 1000:
            raise FocusValidationError(
                "A carta de correção precisa ter de 15 a 1000 caracteres "
                "(tem %d)." % len(texto))
        return self._request('POST', '/v2/nfe/%s/carta_correcao' % ref,
                             body={'correcao': texto})

    # ------------------------------------------------------------------
    # utilidades
    # ------------------------------------------------------------------
    def testar_conexao(self):
        """Confirma token e ambiente sem emitir nada.

        `/v2/empresas` **só existe em produção** -- em homologação ele devolve
        404, o que faria um teste de conexão perfeitamente saudável parecer
        falha. Então em homologação o probe é outro: consultar uma referência
        que não existe. Um 404 "nota não encontrada" prova que o token foi
        aceito (a API chegou a procurar); um 401 prova que não.

        Devolve a lista de emitentes quando dá para obtê-la, e uma lista vazia
        quando o ambiente não expõe esse endpoint.
        """
        if self.ambiente == 'producao':
            empresas = self._request('GET', '/v2/empresas')
            return empresas if isinstance(empresas, list) else []
        try:
            self._request('GET', '/v2/nfe/%s' % PROBE_REF)
        except FocusNotFound:
            pass  # token aceito: é a referência que não existe, e é de propósito
        return []

    def baixar(self, caminho):
        """Baixa XML ou DANFE.

        A consulta devolve caminhos relativos (`caminho_xml_nota_fiscal`,
        `caminho_danfe`); URLs absolutas também aparecem em alguns campos,
        então aceitamos os dois.
        """
        if not caminho:
            return None
        url = caminho if caminho.startswith('http') else self.base_url + caminho
        try:
            response = self.session.request(
                'GET', url, auth=(self.token, ''),
                timeout=self.timeout, verify=self.verify)
        except requests.RequestException as exc:
            raise FocusError("Falha ao baixar %s: %s" % (url, exc)) from exc
        if response.status_code != 200:
            raise FocusError(
                "Falha ao baixar %s (HTTP %s)." % (url, response.status_code),
                status_code=response.status_code)
        return response.content
