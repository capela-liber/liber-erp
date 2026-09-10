# -*- coding: utf-8 -*-
"""O eixo da rede onde se lê: Análise de Vendas e Painel de Notas Fiscais.

O grão dos dois continua a loja; a rede é coluna de leitura. STORED porque
agrupar exige coluna -- e o teste confere exatamente isso: a coluna existe,
carrega o valor, e acompanha a ficha quando a loja muda de rede.
"""
import base64

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestReportAxes(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env["liber.partner.group"].create(
            {"name": "Travessa (eixo teste)"})
        cls.loja = cls.env["res.partner"].create({
            "name": "Travessa Botafogo",
            "vat": "31.004.013/0005-96",
            "partner_group_id": cls.group.id,
        })

    def test_analise_de_vendas_agrupa_pela_rede(self):
        livro = self.env["product.product"].create(
            {"name": "Livro de Teste", "list_price": 50.0})
        order = self.env["sale.order"].create({
            "partner_id": self.loja.id,
            "order_line": [(0, 0, {"product_id": livro.id,
                                   "product_uom_qty": 2})],
        })
        self.env.flush_all()

        rows = self.env["sale.report"].search(
            [("partner_group_id", "=", self.group.id)])

        self.assertTrue(rows, "a linha do pedido deve carregar a rede")
        self.assertIn(self.loja.id, rows.mapped("partner_id").ids,
                      "a linha encontrada é a do pedido da loja")
        self.assertTrue(order.exists())
        self.assertEqual(set(rows.mapped("commercial_group_display")),
                         {"Travessa (eixo teste)"},
                         "o eixo rede-ou-cliente carrega o nome da rede")

    def test_painel_xml_acompanha_a_ficha(self):
        panel = self.env["nfe.xml.panel"].create({
            "file": base64.b64encode(b"<xml/>"),
            "file_name": "dummy.xml",
            "partner_id": self.loja.id,
        })
        self.assertEqual(panel.partner_group_id, self.group)

        # A loja muda de rede: o painel tem de seguir, senão o agrupamento
        # histórico mente.
        outra = self.env["liber.partner.group"].create(
            {"name": "Vila (eixo teste)"})
        self.loja.partner_group_id = outra
        self.assertEqual(panel.partner_group_id, outra)

    def test_ficha_sem_rede_nao_quebra_o_painel(self):
        solta = self.env["res.partner"].create({"name": "Livraria Solta"})
        panel = self.env["nfe.xml.panel"].create({
            "file": base64.b64encode(b"<xml/>"),
            "file_name": "dummy2.xml",
            "partner_id": solta.id,
        })
        self.assertFalse(panel.partner_group_id)
        self.assertEqual(panel.commercial_group_display, "Livraria Solta",
                         "sem rede, o eixo é o próprio cliente")

    def test_dashboard_troca_cliente_por_rede(self):
        """O pivô "Top Customers" do Painel de Vendas passa a agrupar pelo
        eixo rede-ou-cliente -- e SÓ ele: a regra é estreita."""
        Dashboard = self.env["spreadsheet.dashboard"]

        alvo = {"model": "sale.report",
                "rows": [{"fieldName": "partner_id"}],
                "name": "Customer"}
        self.assertTrue(Dashboard._arredar_pivo(alvo))
        self.assertEqual(alvo["rows"][0]["fieldName"],
                         "commercial_group_display")
        self.assertEqual(alvo["name"], "Grupo / Cliente")

        dois_niveis = {"model": "sale.report",
                       "rows": [{"fieldName": "partner_id"},
                                {"fieldName": "product_id"}]}
        self.assertFalse(Dashboard._arredar_pivo(dois_niveis),
                         "pivô de dois níveis é de alguém que quis aquilo")

        outro_modelo = {"model": "res.currency",
                        "rows": [{"fieldName": "partner_id"}]}
        self.assertFalse(Dashboard._arredar_pivo(outro_modelo),
                         "modelo sem o eixo passa intacto")
