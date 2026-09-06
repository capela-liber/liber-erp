# -*- coding: utf-8 -*-
"""O número de fora é o de dentro: o cartão "Faturas sem pedido" e a lista.

Em 06/09/2026 o dono clicou no cartão (79.923) e a lista que abriu somava
34.787; depois, em agosto da Edlab Press, 33.340,82 no cartão contra
34.037,95 na lista. Eram dois defeitos: o cartão era uma conta entre dois
relógios e o clique abria outro recorte; e a lista mostrava o Valor da
DANFE (com frete) onde o cartão soma o líquido dos itens.

Este tour é a prova pela tela, no perfil de quem vai usar (Gerente de
Vendas, não admin): entra no painel, clica no cartão, chega à lista de Notas
sem pedido, e o rodapé da coluna "Valor líquido" mostra o MESMO número que o
cartão soma -- que o motor calcula aqui com o recorte do próprio painel. O
cartão é desenhado em canvas e não tem texto no DOM; por isso o número do
cartão vem do ORM, pelo domínio do JSON, e a tela prova o lado da lista.
"""
import base64
import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "liber_sales_dashboard_tour")
class TestSalesDashboardTour(HttpCase):

    def _nota(self, cliente, valor, invoice=None, frete=0.0):
        nota = self.env["nfe.xml.panel"].create({
            "file": base64.b64encode(b"<nfe/>"), "file_name": "nota.xml",
            "partner_id": cliente.id, "company_id": self.env.company.id,
            "nfe_direction": "out", "cfop_id": self.cfop.id,
            "danfe_value": valor + frete, "shipping_price": frete,
            "file_create_date": self.hoje, "invoice_id": invoice and invoice.id,
        })
        self.env["nfe.xml.items"].create({
            "soc_xml_id": nota.id, "ks_product_name": self.livro.name,
            "ks_product_qty": 1, "ks_price": valor, "net_price": valor})
        return nota

    def test_sales_dashboard_tour(self):
        from odoo import fields
        # As notas nascem no MÊS PASSADO: o período padrão do painel é
        # "últimos 12 meses", que na planilha são os doze meses fechados antes
        # do atual -- uma nota de hoje ficaria fora do cartão e da lista.
        self.hoje = fields.Date.subtract(fields.Date.context_today(self.env.user), months=1)
        empresa = self.env.company
        Cfop = self.env["nfe.cfop"]
        self.cfop = Cfop.search([("document_kind", "=", "sale")], limit=1) \
            or Cfop.create({"code": "5101", "document_kind": "sale"})
        self.livro = self.env["product.product"].create({
            "name": "Livro do Tour", "type": "consu", "list_price": 100.0})
        ligada = self.env["res.partner"].create({"name": "Livraria Ligada"})
        solta = self.env["res.partner"].create({"name": "Livraria Solta"})
        sem = self.env["res.partner"].create({"name": "Livraria Sem Fatura"})

        # 1. nota cuja fatura está ligada a um pedido: fora do cartão
        pedido = self.env["sale.order"].create({
            "partner_id": ligada.id,
            "order_line": [(0, 0, {"product_id": self.livro.id, "product_uom_qty": 1})]})
        pedido.action_confirm()
        pedido.order_line.qty_delivered = 1
        fatura_ligada = pedido._create_invoices()
        fatura_ligada.action_post()
        self._nota(ligada, 100.0, invoice=fatura_ligada)
        # 2. nota com fatura solta (sem pedido): dentro -- com frete, para
        #    provar que o rodapé lê o líquido e não a DANFE
        fatura_solta = self.env["account.move"].create({
            "move_type": "out_invoice", "partner_id": solta.id,
            "invoice_line_ids": [(0, 0, {"product_id": self.livro.id,
                                         "quantity": 1, "price_unit": 90.0})]})
        self._nota(solta, 90.0, invoice=fatura_solta, frete=15.0)
        # 3. nota sem fatura nenhuma: dentro
        self._nota(sem, 60.0)
        # 4. nota sem fatura de DOIS ANOS atrás: fora do período do painel.
        #    O clique tem de levar o período para a lista -- sem isso ela
        #    chegava inteira, de 2019 em diante.
        velha = self.env["res.partner"].create({"name": "Livraria Velha"})
        nota_velha = self._nota(velha, 999.0)
        nota_velha.file_create_date = fields.Date.subtract(self.hoje, years=2)

        # O que o cartão soma, pelo recorte do próprio JSON do painel.
        painel = self.env.ref("spreadsheet_dashboard_sale.spreadsheet_dashboard_sales")
        planilha = json.loads(base64.b64decode(painel.spreadsheet_binary_data))
        [pivo] = [p for p in planilha["pivots"].values() if p["name"] == "Notas sem pedido"]
        [(cartao,)] = self.env["nfe.xml.panel"]._read_group(
            list(pivo["domain"]) + [("partner_id", "in", (ligada | solta | sem | velha).ids)],
            aggregates=["net_value:sum"])
        self.assertEqual(cartao, 150.0 + 999.0,
                         "sem período, o recorte pega a velha também: é o filtro que a tira")

        gerente = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Gerente de Vendas do Tour", "login": "gerente_tour",
            "password": "gerente_tour", "lang": "en_US",
            "company_id": empresa.id, "company_ids": [(6, 0, [empresa.id])],
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("sales_team.group_sale_manager").id])],
        })
        self.assertTrue(gerente.exists())
        self.start_tour("/odoo", "liber_sales_dashboard_tour", login="gerente_tour")
