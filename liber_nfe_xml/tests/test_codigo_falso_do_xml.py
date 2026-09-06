# -*- coding: utf-8 -*-
"""Nem tudo que vem no lugar do código do produto é código de produto.

A NFe traz o código do item em `cProd` e o de barras em `cEAN`. Dois valores
aparecem ali e não identificam livro nenhum:

  SEM GTIN    o literal da própria NFe para "item sem código de barras".
              Tomado por código, colapsava todo item sem barras num produto só.
  CFOP5102    o Olist emite a nota com `cProd` = a CFOP quando o livro não tem
              código interno do lado deles.

O segundo custou caro (05/09/2026): o leitor criou um produto chamado
"CFOP5102" com o nome do primeiro livro que passou, e toda nota seguinte com o
mesmo `cProd` casou com ele. Eram dois registros -- `CFOP5102` e `CFOP6102`,
ambos chamados "Os cantos do homem-sombra" -- em 50 linhas de fatura e zero
linhas de pedido. A fatura saía com o livro errado, e o pedido do marketplace
ficava para sempre em "A faturar".

Recusar o código é melhor que inventar produto: sem código o item fica sem
produto, e quem emite a nota vê o problema em vez de herdar um documento
errado.
"""
from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_nfe_xml.models.soc_xml_panel import _e_codigo_falso


@tagged('post_install', '-at_install')
class TestCodigoFalsoDoXml(TransactionCase):

    # -- o que tem de ser recusado -----------------------------------------
    def test_sem_gtin_e_falso(self):
        self.assertTrue(_e_codigo_falso("SEM GTIN"))
        self.assertTrue(_e_codigo_falso("sem gtin"))
        self.assertTrue(_e_codigo_falso("  SEM GTIN  "))
        self.assertTrue(_e_codigo_falso("SEMGTIN"))

    def test_cfop_e_falso(self):
        for codigo in ("CFOP5102", "CFOP6102", "cfop5102", "CFOP 5102"):
            self.assertTrue(_e_codigo_falso(codigo),
                            "%s não identifica livro nenhum" % codigo)

    def test_vazio_e_falso(self):
        self.assertTrue(_e_codigo_falso(""))
        self.assertTrue(_e_codigo_falso(None))

    # -- o que tem de passar ------------------------------------------------
    def test_isbn_passa(self):
        self.assertFalse(_e_codigo_falso("9786551590115"))
        self.assertFalse(_e_codigo_falso("978-65-5159-011-5"))

    def test_codigo_interno_da_casa_passa(self):
        self.assertFalse(_e_codigo_falso("N1-0042"))

    def test_cfop_solto_nao_e_recusado(self):
        """A borda que decide o recorte.

        "5102" sozinho é ambíguo: pode ser CFOP e pode ser código interno de
        quatro dígitos de algum fornecedor. Recusar quatro dígitos quaisquer
        seria perder código legítimo para consertar um caso conhecido. O
        recorte fica no prefixo CFOP, que é inequívoco."""
        self.assertFalse(_e_codigo_falso("5102"))
