# -*- coding: utf-8 -*-
"""Shared fixture: an author, a work with an ISBN, a contract with two tiers
and a small legacy CSV written to a temp file in the shape of the unified
base (same header, same conventions: empty cell = unknown, ';' flags)."""
import csv
import os
import tempfile
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase

HEADER = ["fonte", "nf", "data_emissao", "ano", "mes", "cnpj_cpf", "cliente",
          "isbn_ean", "codigo_interno", "titulo", "titulo_original", "autor",
          "editora_selo", "quantidade", "qtde_origem", "preco_capa",
          "valor_bruto", "desconto", "valor_liquido", "valor_liquido_estimado",
          "valor_total_nota", "cfop", "cfop_descricao", "natureza_operacao",
          "status_nf", "flags"]
ISBN = "9788577150001"


def row(**kw):
    base = {k: "" for k in HEADER}
    base.update({"fonte": "Sistema antigo (1999-2016)", "isbn_ean": ISBN,
                 "titulo": "Dom Casmurro", "titulo_original": "Dom Casmurro",
                 "qtde_origem": "INFORMADA"})
    base.update(kw)
    if base["data_emissao"] and not base["ano"]:
        base["ano"] = base["data_emissao"][:4]
        base["mes"] = str(int(base["data_emissao"][5:7]))
    return [base[k] for k in HEADER]


def write_csv(rows, header=None):
    """Write ``rows`` under the unified header to a temp CSV; returns the path."""
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8-sig", newline="")
    writer = csv.writer(handle)
    writer.writerow(header or HEADER)
    writer.writerows(rows)
    handle.close()
    return handle.name


class LegacyCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        cls.author = cls.env["res.partner"].create({"name": "Machado de Assis"})
        cls.book = cls.env["product.template"].create({
            "name": "Dom Casmurro", "type": "consu", "list_price": 10.0,
            "barcode": ISBN})
        cls.ipca = cls.env.ref("liber_copyright_contracts_legacy.price_index_ipca")
        cls.contract = cls.env["edlab.contract"].create({
            "signature_date": today - timedelta(days=30),
            "expiration_date": today + timedelta(days=365),
            "royalty_line_ids": [(0, 0, {
                "partner_id": cls.author.id,
                "product_id": cls.book.id,
                "tier_ids": [
                    (0, 0, {"qty_from": 0, "qty_to": 100, "percentage": 7.0}),
                    (0, 0, {"qty_from": 101, "qty_to": 0, "percentage": 8.0}),
                ],
            })],
        })
        cls.royalty = cls.contract.royalty_line_ids
        cls.royalty.action_create_analytic_account()
        cls.account = cls.royalty.analytic_account_id
        cls.Sale = cls.env["edlab.legacy.sale"]
        cls._tmp = []

    @classmethod
    def tearDownClass(cls):
        for path in cls._tmp:
            if os.path.exists(path):
                os.unlink(path)
        super().tearDownClass()

    @classmethod
    def write_csv(cls, rows, header=None):
        path = write_csv(rows, header)
        cls._tmp.append(path)
        return path

    def legacy_lines(self):
        return self.env["account.analytic.line"].search(
            [("edlab_legacy_line_id", "=", self.royalty.id)], order="date")

    # The base, in miniature. Everything the CSV can throw: a shipment, two
    # settlements, a straight sale, a return, a donation, a cancelled note,
    # a row without CFOP that the wording still classifies, a duplicate.
    SAMPLE = [
        row(nf="1", data_emissao="2005-03-10", quantidade="50", cfop="5917",
            natureza_operacao="REMESSA em consignação", valor_liquido="500.0",
            valor_liquido_estimado="500.0"),
        row(nf="2", data_emissao="2005-03-20", quantidade="30", cfop="5113",
            natureza_operacao="VENDA - acerto de consignação",
            preco_capa="10.0", valor_bruto="300.0",
            valor_liquido="240.0", valor_liquido_estimado="240.0"),
        row(nf="3", data_emissao="2005-04-05", quantidade="80", cfop="6113",
            natureza_operacao="VENDA - acerto de consignação",
            preco_capa="10.0", valor_bruto="800.0",
            valor_liquido="640.0", valor_liquido_estimado="640.0"),
        row(nf="4", data_emissao="2005-04-15", quantidade="10", cfop="5101",
            natureza_operacao="VENDA (produção própria)",
            preco_capa="10.0", valor_bruto="100.0",
            valor_liquido="100.0", valor_liquido_estimado="100.0"),
        row(nf="5", data_emissao="2005-05-02", quantidade="5", cfop="1201",
            natureza_operacao="DEVOLUÇÃO de venda (entrada)",
            valor_liquido="50.0", valor_liquido_estimado="50.0"),
        row(nf="6", data_emissao="2005-05-09", quantidade="20", cfop="5910",
            natureza_operacao="DOAÇÃO / BRINDE", valor_liquido="0.0",
            valor_liquido_estimado="0.0"),
        row(nf="7", data_emissao="2005-05-20", quantidade="15", cfop="5101",
            natureza_operacao="VENDA (produção própria)",
            valor_liquido="150.0", valor_liquido_estimado="150.0",
            status_nf="Cancelada", flags="NF_SEM_EFEITO_FISCAL"),
        row(nf="8", data_emissao="2005-06-01", quantidade="4", cfop="",
            natureza_operacao="VENDA - acerto de consignação",
            valor_liquido="40.0", valor_liquido_estimado="40.0"),
        row(nf="8", data_emissao="2005-06-01", quantidade="4", cfop="",
            natureza_operacao="VENDA - acerto de consignação",
            valor_liquido="40.0", valor_liquido_estimado="40.0",
            flags="POSSIVEL_DUPLICATA_EXATA"),
        row(nf="9", data_emissao="2005-06-15", quantidade="7", cfop="5101",
            isbn_ean="", titulo="Livro sem ISBN", titulo_original="Livro sem ISBN",
            natureza_operacao="VENDA (produção própria)",
            valor_liquido="70.0", valor_liquido_estimado="70.0", flags="SEM_ISBN"),
    ]
