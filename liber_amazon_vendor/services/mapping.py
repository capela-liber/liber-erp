# -*- coding: utf-8 -*-
"""
Do purchase order da Amazon para os campos do Odoo.

A tradução que dá nome à confusão: no Vendor Central **a Amazon compra**. O
que a SP-API chama de `purchaseOrder` é o pedido *dela*, e do lado de cá é uma
VENDA. Guardar isso como `purchase.order` inverteria estoque e faturamento --
por isso a cotação que sai daqui é `sale.order`, e o espelho do documento da
Amazon é um modelo nosso, que não pretende ser nem uma coisa nem outra.

É lógica pura de propósito: nenhum import do Odoo, nenhuma ida ao banco. A
parte que erra em silêncio -- parse de data, campo aninhado, moeda -- se testa
em milissegundos, e o TransactionCase fica só para o que grava.
"""

from datetime import datetime, timezone


# Os três estados que a Vendor API documenta hoje. A lista serve para
# *classificar*, nunca para rejeitar: estado desconhecido passa e fica marcado,
# que é uma falha que se lê no relatório em vez de sumir. O agregador que veio
# antes levantava exceção aqui, e o dia em que a Amazon inventasse um quarto
# estado o pedido inteiro se perderia.
KNOWN_STATES = ("New", "Acknowledged", "Closed")

# Estados em que o pedido ainda vale como compromisso. "Closed" já foi
# entregue ou cancelado pela Amazon -- tratá-lo como aberto criaria demanda
# fantasma.
OPEN_STATES = ("New", "Acknowledged")


def parse_amazon_datetime(value):
    """
    Converte data ISO 8601 da SP-API em datetime UTC ingênuo, ou None.

    Ingênuo porque é assim que o Odoo guarda: todo datetime no banco é UTC sem
    fuso, e gravar um datetime com tzinfo levanta erro na hora de escrever.

    A Amazon manda 'Z' onde o Python quer '+00:00' e às vezes manda campo
    vazio em vez de omitir. Data ruim vira None em vez de exceção: um pedido
    sem janela de entrega ainda é um pedido, e derrubá-lo por causa disso
    perde a venda para salvar o calendário.
    """
    if value in (None, False, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def parse_delivery_window(window):
    """
    Abre o `deliveryWindow`, que vem como duas datas coladas por '--'.

    Devolve (início, fim). Formato inesperado devolve (None, None) -- não é
    erro, é ausência de janela.
    """
    if not window or "--" not in str(window):
        return None, None
    start_text, _, end_text = str(window).partition("--")
    return parse_amazon_datetime(start_text), parse_amazon_datetime(end_text)


def normalize_isbn(value):
    """
    Tira hífen e espaço para comparar com o barcode do cadastro.

    Necessário nos dois lados: há barcode gravado com hífen no banco, e a
    comparação crua faria o título existente passar por inexistente -- o pior
    tipo de erro aqui, porque produz um relatório de "faltando no cadastro"
    que manda alguém cadastrar o que já está cadastrado.
    """
    if not value:
        return ""
    return str(value).replace("-", "").replace(" ", "").strip()


def map_item(item):
    """
    Traduz uma linha do PO.

    Duas escolhas que não são óbvias:

    `price_unit` sai de **netCost**, não de listPrice. netCost é o que a
    Amazon paga para nós; listPrice é a etiqueta com que ela revende. Trocar
    os dois infla a receita do pedido inteiro e só aparece no fechamento do
    mês.

    `isbn` sai de **vendorProductIdentifier** -- o identificador que NÓS demos
    ao título, que para livro é o ISBN-13 e casa com o barcode do
    product.product. `amazonProductIdentifier` é o ASIN, código interno da
    Amazon, que não existe no nosso cadastro.
    """
    ordered = item.get("orderedQuantity") or {}
    net_cost = item.get("netCost") or {}
    list_price = item.get("listPrice") or {}

    return {
        "item_sequence": (item.get("itemSequenceNumber") or "").strip(),
        "isbn": normalize_isbn(item.get("vendorProductIdentifier")) or None,
        "asin": (item.get("amazonProductIdentifier") or "").strip() or None,
        "quantity": ordered.get("amount") or 0,
        "uom": ordered.get("unitOfMeasure"),
        "price_unit": net_cost.get("amount"),
        "currency": net_cost.get("currencyCode") or list_price.get("currencyCode"),
        "list_price": list_price.get("amount"),
        "backorder_allowed": bool(item.get("isBackOrderAllowed", False)),
    }


def map_purchase_order(order):
    """
    Traduz um purchase order inteiro.

    Não decide nada sobre produto nem parceiro: isso depende do banco e é
    trabalho do modelo. Aqui só se resolve o que é forma do dado.
    """
    details = order.get("orderDetails") or {}
    state = order.get("purchaseOrderState") or ""
    window_start, window_end = parse_delivery_window(details.get("deliveryWindow"))

    return {
        "name": (order.get("purchaseOrderNumber") or "").strip(),
        "amazon_state": state,
        "state_known": state in KNOWN_STATES,
        "is_open": state in OPEN_STATES,
        "order_date": parse_amazon_datetime(details.get("purchaseOrderDate")),
        "state_changed_date": parse_amazon_datetime(
            details.get("purchaseOrderStateChangedDate")),
        "order_type": details.get("purchaseOrderType"),
        "payment_method": details.get("paymentMethod"),
        "buying_party": (details.get("buyingParty") or {}).get("partyId"),
        "selling_party": (details.get("sellingParty") or {}).get("partyId"),
        "ship_to_party": (details.get("shipToParty") or {}).get("partyId"),
        "delivery_start": window_start,
        "delivery_end": window_end,
        "lines": [map_item(item) for item in (details.get("items") or [])],
    }


def order_total(mapped):
    """Soma quantidade × netCost das linhas. Linha sem preço conta como zero."""
    total = 0.0
    for line in mapped.get("lines") or []:
        price = line.get("price_unit")
        if price is None:
            continue
        total += float(price) * (line.get("quantity") or 0)
    return round(total, 2)


def import_report(orders):
    """
    Diz o que dá para importar e o que vai travar, antes de gravar.

    Existe porque o problema real da importação não é a Amazon, é o nosso
    cadastro: título com ISBN que não está em product.product não vira linha
    de cotação, e descobrir isso no meio de um cron é o pior momento. Este
    relatório é o que o assistente mostra antes de confirmar.
    """
    mapped = [map_purchase_order(order) for order in orders]

    isbns = set()
    lines_without_isbn = 0
    unknown_states = set()

    for order in mapped:
        if not order["state_known"]:
            unknown_states.add(order["amazon_state"] or "(empty)")
        for line in order["lines"]:
            if line["isbn"]:
                isbns.add(line["isbn"])
            else:
                lines_without_isbn += 1

    return {
        "orders": len(mapped),
        "open_orders": sum(1 for o in mapped if o["is_open"]),
        "lines": sum(len(o["lines"]) for o in mapped),
        "isbns": sorted(isbns),
        "lines_without_isbn": lines_without_isbn,
        "unknown_states": sorted(unknown_states),
        "total": round(sum(order_total(o) for o in mapped), 2),
        "mapped": mapped,
    }
