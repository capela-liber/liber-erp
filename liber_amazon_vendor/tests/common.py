# -*- coding: utf-8 -*-
"""Base dos testes: uma conta, um catálogo pequeno e payloads de mentira.

Nada de dado de demo do core -- ele muda entre versões e transforma teste
quebrado em caça ao tesouro. Tudo que os testes usam nasce aqui.
"""

from odoo.tests import TransactionCase


def amazon_item(sequence, isbn, qty=10, net_cost="45.50", currency="BRL",
                asin=None, list_price="89.90"):
    """Uma linha no formato exato que a SP-API devolve."""
    item = {
        "itemSequenceNumber": sequence,
        "amazonProductIdentifier": asin or "B0%s" % sequence.zfill(8),
        "vendorProductIdentifier": isbn,
        "orderedQuantity": {"amount": qty, "unitOfMeasure": "Eaches"},
        "isBackOrderAllowed": False,
    }
    if net_cost is not None:
        item["netCost"] = {"amount": net_cost, "currencyCode": currency}
    if list_price is not None:
        item["listPrice"] = {"amount": list_price, "currencyCode": currency}
    return item


def amazon_order(number, items, state="Acknowledged",
                 order_date="2026-07-01T10:00:00Z",
                 window="2026-07-10T00:00:00Z--2026-07-20T00:00:00Z"):
    """Um purchase order no formato exato que a SP-API devolve."""
    details = {
        "purchaseOrderDate": order_date,
        "purchaseOrderStateChangedDate": order_date,
        "purchaseOrderType": "RegularOrder",
        "paymentMethod": "Invoice",
        "buyingParty": {"partyId": "AMZN_BR"},
        "sellingParty": {"partyId": "VENDOR_1"},
        "shipToParty": {"partyId": "CD_CAJAMAR"},
        "items": items,
    }
    if window:
        details["deliveryWindow"] = window
    return {
        "purchaseOrderNumber": number,
        "purchaseOrderState": state,
        "orderDetails": details,
    }


class AmazonVendorCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # A empresa escritura em real porque é o caso real: editora
        # brasileira vendendo para a Amazon Brasil, que paga em BRL. Base
        # recém-criada nasce em USD, e deixar assim faria o teste de moeda
        # provar o contrário do que a operação vive.
        cls.currency = cls.env.ref('base.BRL')
        cls.currency.active = True
        cls.company.currency_id = cls.currency
        cls.currency_name = cls.company.currency_id.name

        cls.partner_amazon = cls.env['res.partner'].create({
            'name': 'Amazon Serviços de Varejo do Brasil',
            'is_company': True,
        })

        cls.account = cls.env['liber.amazon.account'].create({
            'name': 'Test Vendor BR',
            'region': 'BR',
            'company_id': cls.company.id,
            'partner_id': cls.partner_amazon.id,
            'client_id': 'amzn1.application-oa2-client.test',
            'client_secret': 'amzn1.oa2-cs.v1.test',
            'refresh_token': 'Atzr|test',
        })

        # Dois títulos no cadastro. O segundo tem barcode COM hífen de
        # propósito: é assim que parte do catálogo real está gravada, e a
        # comparação crua o daria por inexistente.
        cls.book_a = cls.env['product.product'].create({
            'name': 'Memórias Póstumas de Brás Cubas',
            'type': 'consu',
            'barcode': '9786551590016',
            'list_price': 89.90,
        })
        cls.book_b = cls.env['product.product'].create({
            'name': 'O Ateneu',
            'type': 'consu',
            'barcode': '978-65-5159-008-5',
            'list_price': 79.90,
        })
        # 9788500000009 fica FORA do cadastro de propósito.

    def _sync(self, orders, account=None):
        return self.env['liber.amazon.order']._sync_from_amazon(
            account or self.account, orders)

    def _order(self, name):
        return self.env['liber.amazon.order'].search([('name', '=', name)])
