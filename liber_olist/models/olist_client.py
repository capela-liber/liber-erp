# -*- coding: utf-8 -*-
"""Thin client for the Olist/Tiny API v2.

v2 (single token) rather than v3 (OAuth2) on purpose: v3's refresh_token lives
for a single day, so an integration that idles over a long weekend needs a human
to re-authorise in a browser. v2 is frozen but has no announced end of life, and
for a read-only feed it is the honest trade. See liber_olist/NOTES.md section 5.
"""
import json
import logging
import time
import urllib.parse
import urllib.request

_logger = logging.getLogger(__name__)

API_URL = "https://api.tiny.com.br/api2"

# The rate limit is per ACCOUNT, not per application: the ERP itself and the
# marketplaces share this budget with us.
#
# 1.1s was a guess from the docs' 60 req/min and it is NOT enough: on
# 2026-08-13 a full read of the catalogue died halfway with "API Bloqueada -
# Excedido o número de acessos". The ceiling of our account is not knowable
# from documentation (the tables still use legacy plan names - NOTES.md §9.2),
# so this number is empirical: 2.2s fits inside 30 req/min, the floor of the
# grid, and left room for the ERP and the marketplaces alongside us.
REQUEST_DELAY = 2.2

# O estrangulamento NÃO chega como erro de rede: vem HTTP 200, com o erro
# dentro do envelope. Tratar isso como falha definitiva é o que faz uma
# varredura de mil chamadas morrer na metade e parecer "a conta não tem esse
# dado" (§6-bis, lição 2).
THROTTLE_MARK = "api bloqueada"
THROTTLE_BACKOFF = 90


class OlistError(Exception):
    pass


# O instante da última chamada, para espaçar as PRÓXIMAS em vez de dormir
# depois de cada uma. A diferença é grande: a chamada de rede leva ~0,4s, e
# dormir 2,2s ao FIM significava que ler o detalhe de UM pedido custava 2,7s,
# dos quais 2,3s eram espera para ninguém. Espaçando pelo relógio, o ritmo
# sustentado continua o mesmo e a chamada avulsa sai na velocidade da rede.
#
# É por processo: com vários workers varrendo ao mesmo tempo o ritmo real
# dobraria. Hoje quem varre é um só (o botão de quem está olhando, ou o cron).
_ultima_chamada = 0.0


def _aguarda_a_vez():
    """Dorme só o que falta para respeitar o espaçamento desde a última chamada."""
    global _ultima_chamada
    falta = REQUEST_DELAY - (time.monotonic() - _ultima_chamada)
    if falta > 0:
        time.sleep(falta)
    _ultima_chamada = time.monotonic()


def call(token, endpoint, **params):
    """POST to a v2 endpoint. Returns the raw response text.

    Not every endpoint answers JSON (nota.fiscal.obter.xml.php answers XML), so
    decoding is left to the caller.
    """
    body = urllib.parse.urlencode(
        {"token": token, "formato": "json", **params}).encode()
    req = urllib.request.Request(
        "%s/%s" % (API_URL, endpoint), data=body, method="POST")
    last_exc = None
    for attempt in range(4):
        try:
            _aguarda_a_vez()
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - network flakiness, not logic
            last_exc = exc
            wait = 5 * (attempt + 1)
            _logger.warning("Olist %s failed (%s); retrying in %ss",
                            endpoint, exc, wait)
            time.sleep(wait)
    raise OlistError("Olist %s failed after retries: %s" % (endpoint, last_exc))


def call_json(token, endpoint, attempts=6, **params):
    """Como `call`, mas insistindo enquanto a resposta for estrangulamento.

    A cota estourada volta como HTTP 200 com `status: Erro` — indistinguível,
    para quem só olha o código HTTP, de "não existe esse registro". Quem chama
    está quase sempre num laço longo (mil notas, seiscentos saldos), e desistir
    no primeiro bloqueio perde a varredura inteira e ainda mente sobre o
    motivo. Erro de verdade (token inválido, id inexistente) continua
    estourando na hora.
    """
    for tentativa in range(attempts):
        payload = json.loads(call(token, endpoint, **params))["retorno"]
        if payload.get("status") == "OK":
            return payload
        detalhe = str(payload.get("erros") or payload.get("codigo_erro") or '')
        if THROTTLE_MARK in detalhe.lower():
            espera = THROTTLE_BACKOFF * (tentativa + 1)
            _logger.warning(
                "Olist %s: cota estourada; pausa de %ss e continua.",
                endpoint, espera)
            time.sleep(espera)
            continue
        raise OlistError("Olist %s: %s" % (endpoint, payload.get("erros")))
    raise OlistError("Olist %s: bloqueado por cota após %s tentativas"
                     % (endpoint, attempts))


def list_notas(token):
    """Every nota fiscal in the account, walking all pages."""
    page, pages = 1, 1
    while page <= pages:
        payload = call_json(token, "notas.fiscais.pesquisa.php", pagina=page)
        pages = int(payload.get("numero_paginas") or 1)
        for item in payload.get("notas_fiscais", []):
            yield item["nota_fiscal"]
        page += 1


def list_produtos(token):
    """Every product in the account, walking all pages."""
    page, pages = 1, 1
    while page <= pages:
        payload = call_json(token, "produtos.pesquisa.php", pagina=page)
        pages = int(payload.get("numero_paginas") or 1)
        for item in payload.get("produtos", []):
            yield item["produto"]
        page += 1


def get_produto(token, id_produto):
    """A ficha COMPLETA do produto no Olist (52 campos). Leitura.

    O que a listagem do catálogo não traz: preço, situação, marca, categoria,
    NCM, pesos e dimensões, descrição, SEO e anexos. É a ficha que a tela de
    Produtos mostra para se decidir o que fazer com o livro.

    None quando o Olist recusa: quem chama está num laço sobre linhas
    escolhidas, e um produto problemático não pode derrubar os outros.
    """
    try:
        return call_json(token, "produto.obter.php",
                         id=id_produto).get("produto") or {}
    except OlistError as exc:
        _logger.warning("Olist produto %s: %s", id_produto, exc)
        return None


def create_produto(token, ficha):
    """Cria um produto no Olist. ESCRITA no catálogo vivo.

    O caminho inverso do módulo: aqui o Odoo povoa o catálogo de lá, e é a
    única vez em que isso acontece. Mesmo duplo-embrulho do resto da v2.
    """
    corpo = json.dumps({"produto": ficha})
    raw = call(token, "produto.incluir.php", produto=corpo)
    return corpo, raw


def update_produto(token, ficha):
    """Reescreve a ficha do produto no Olist. Isto é ESCRITA no catálogo vivo.

    **Manda a ficha INTEIRA, sempre.** Não se sabe (e a documentação não diz)
    se `produto.alterar` faz atualização parcial ou substituição; mandar só o
    campo que mudou seria apostar que é parcial, e o preço dessa aposta é
    apagar peso, NCM, descrição e SEO de um livro do catálogo. Ler a ficha,
    trocar um campo e devolver tudo funciona nas duas hipóteses.

    Devolve (corpo_enviado, resposta_crua) para que a tela guarde as duas
    pontas: numa escrita, poder reler o que foi dito e o que voltou é o mínimo
    (a lição do §6-quater).
    """
    corpo = json.dumps({"produto": ficha})
    raw = call(token, "produto.alterar.php", produto=corpo)
    return corpo, raw


def list_pedidos(token, desde=None):
    """Os pedidos da conta, percorrendo as páginas. Leitura.

    A LISTAGEM é barata (uma chamada por 100 pedidos) e traz o essencial —
    id, número, data, cliente, situação, valor e `numero_ecommerce`. O que ela
    NÃO traz é o canal de venda: `nomeEcommerce` só existe no detalhe
    (`pedido.obter`), uma chamada por pedido. Daí a divisão em dois passos, e
    daí o espelho: varrer ~1000 pedidos de detalhe são ~36 minutos de cota, e
    isso não pode ser o preço de abrir uma tela.

    `desde` (dd/mm/aaaa) limita pela data do pedido — é o que o cron usa para
    não reler o histórico inteiro toda noite.
    """
    page, pages = 1, 1
    while page <= pages:
        params = {"pagina": page}
        if desde:
            params["dataInicial"] = desde
        payload = call_json(token, "pedidos.pesquisa.php", **params)
        pages = int(payload.get("numero_paginas") or 1)
        for item in payload.get("pedidos", []):
            yield item["pedido"]
        page += 1


def get_pedido(token, id_pedido):
    """O detalhe de UM pedido: itens, cliente, nota e o bloco `ecommerce`.

    É aqui que mora o canal de venda (`ecommerce.nomeEcommerce`) — e o campo
    se chama assim mesmo, não `canalVenda` como supunha a pesquisa de papel
    (NOTES.md §5, corrigido em §12). Também traz `id_nota_fiscal`, que é o que
    liga o pedido à nota que já importamos.

    Devolve None quando o Olist recusa: quem chama está num laço sobre linhas
    escolhidas, e um pedido problemático não pode derrubar os outros.
    """
    try:
        return call_json(token, "pedido.obter.php", id=id_pedido).get("pedido") or {}
    except OlistError as exc:
        _logger.warning("Olist pedido %s: %s", id_pedido, exc)
        return None


def get_estoque(token, id_produto):
    """Saldo de UM produto no Olist. Leitura.

    Devolve o bloco `produto` (`saldo`, `saldoReservado`, `depositos`) ou None
    quando o Olist recusa a consulta. `None` em vez de exceção porque quem
    chama está sempre num laço sobre linhas escolhidas: um produto que o Olist
    não conhece não pode derrubar a leitura dos outros.
    """
    try:
        return call_json(token, "produto.obter.estoque.php",
                         id=id_produto).get("produto") or {}
    except OlistError as exc:
        _logger.warning("Olist estoque do produto %s: %s", id_produto, exc)
        return None


def list_atualizacoes_estoque(token, desde):
    """Produtos cujo estoque MUDOU no Olist desde `desde` (dd/mm/aaaa hh:mm:ss).

    A janela incremental — o que torna possível um cron de 4x ao dia. Ler o
    saldo de todo o catálogo custa uma chamada por livro (~580, ~20 min); esta
    custa uma e devolve só o que se mexeu, que num dia normal é um punhado.

    Conta vazia responde `status: Erro` com "A consulta não retornou
    registros": isso é ZERO alterações, não falha. Tratar como erro faria o
    cron gritar todo dia em que ninguém vendeu nada.
    """
    try:
        payload = call_json(token, "lista.atualizacoes.estoque.php",
                            dataAlteracao=desde)
    except OlistError as exc:
        if "não retornou registros" in str(exc):
            return []
        raise
    return [item.get("produto", item)
            for item in (payload.get("produtos") or [])]


def find_produto_id(token, codigo):
    """Resolve an Olist internal product id from its `codigo` (the ISBN).

    The stock endpoint keys on Olist's INTERNAL id, not on the ISBN, but every
    other place we touch a product uses the ISBN (it is the book's own
    identity). This bridges the two: one narrowed search page, matched exactly
    on `codigo` so a substring hit on another book's code never wins.
    Returns the id as a string, or None.
    """
    codigo = (codigo or '').strip()
    if not codigo:
        return None
    payload = call_json(token, "produtos.pesquisa.php", pesquisa=codigo)
    for item in payload.get("produtos", []):
        prod = item["produto"]
        if (prod.get("codigo") or '').strip() == codigo:
            return str(prod.get("id"))
    return None


def update_estoque(token, id_produto, quantidade, tipo='B',
                   deposito=None, observacoes=None):
    """Set/adjust one product's stock in Olist. This is a WRITE call.

    Keyed by Olist's INTERNAL product id (idProduto): the v2 stock endpoint
    does NOT accept the SKU/codigo, unlike the emission path. tipo='B'
    (balanco) makes `quantidade` the absolute on-hand in Olist - our real
    stock becomes theirs, rather than being added to it.

    The `estoque` envelope is JSON, NOT the XML the docs show: `call` always
    sends formato=json, and under formato=json this endpoint wants the payload
    in JSON too. The first live push proved it - an XML envelope came back as
    "ERRO JSON mal formado ou invalido" (codigo_erro 3). The double-wrap is the
    v2 idiom for every write: the param IS `estoque`, and its value is
    `{"estoque": {...}}` - same shape as `produto.alterar`.

    Returns (request_body, raw_response_text) so the caller can keep both as
    evidence - a stock write is a side effect worth inspecting after the fact.
    """
    estoque = {
        "idProduto": int(id_produto),
        "tipo": tipo,
        "quantidade": float(quantidade),
    }
    if deposito:
        estoque["deposito"] = deposito[:100]
    if observacoes:
        estoque["observacoes"] = observacoes[:100]
    request_body = json.dumps({"estoque": estoque})
    raw = call(token, "produto.atualizar.estoque.php", estoque=request_body)
    return request_body, raw


def get_nota_xml(token, nota_id, attempts=6):
    """The NFe XML of one nota, unwrapped. Returns bytes, or None.

    Two traps live in this one call:

    1. Under throttling the API answers HTTP 200 with an error payload INSTEAD
       of the XML - indistinguishable from "this note has no XML" if you only
       look at the body. So a missing <xml_nfe> is treated as a TEMPORARY
       failure and retried; treating it as "no XML" silently dropped 155 of 705
       notes on the first run.
    2. The XML arrives nested inside <retorno><xml_nfe>...</xml_nfe></retorno>.
       It is cut out by bytes, never re-parsed and re-serialised: round-tripping
       through ElementTree rewrites the namespaces and INVALIDATES THE DIGITAL
       SIGNATURE of the NFe.
    """
    for attempt in range(attempts):
        raw = call(token, "nota.fiscal.obter.xml.php", id=nota_id).encode("utf-8")
        start = raw.find(b"<xml_nfe>")
        end = raw.rfind(b"</xml_nfe>")
        if start != -1 and end != -1:
            return raw[start + len(b"<xml_nfe>"):end].strip()
        wait = 10 * (attempt + 1)
        _logger.warning("Olist nota %s: no <xml_nfe> (throttled?); waiting %ss",
                        nota_id, wait)
        time.sleep(wait)
    return None
