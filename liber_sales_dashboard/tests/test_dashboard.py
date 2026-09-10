# -*- coding: utf-8 -*-
"""Vendas × Notas: o que cada gráfico promete somar, e para quem o painel abre.

O painel é uma planilha -- o desenho não se testa. O que se prova é o recorte
que sustenta cada número: o gráfico de cima soma pedido confirmado e não soma
cotação; o de baixo soma nota emitida por nós com CFOP de venda ou acerto, e
não soma nota cancelada, nota de fornecedor (que também traz CFOP 5101 -- o
CFOP é do emissor) nem remessa. Os domínios saem do próprio JSON que vai para
a tela: se o arquivo mudar e o teste não, o teste passa a medir outra coisa.
"""
import base64
import json

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


@tagged("post_install", "-at_install", "liber_sales_dashboard")
class TestSalesDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.painel = cls.env.ref("spreadsheet_dashboard_sale.spreadsheet_dashboard_sales")
        cls.planilha = json.loads(base64.b64decode(
            cls.painel.spreadsheet_binary_data))
        cls.cliente = cls.env["res.partner"].create({"name": "Livraria do Painel"})
        cls.livro = cls.env["product.product"].create({
            "name": "Livro do painel", "type": "consu", "list_price": 100.0})
        Cfop = cls.env["nfe.cfop"]
        cls.cfop_venda = Cfop.search([("document_kind", "=", "sale")], limit=1) \
            or Cfop.create({"code": "5101", "document_kind": "sale"})
        cls.cfop_remessa = Cfop.search(
            [("document_kind", "=", "consignment")], limit=1) \
            or Cfop.create({"code": "5917", "document_kind": "consignment"})

    # -- as fontes, lidas do JSON ------------------------------------------
    def _grafico(self, trecho):
        for fig in self.planilha["sheets"][0]["figures"]:
            dados = fig["data"]
            if dados["type"] == "odoo_bar" and trecho in dados["title"]["text"]:
                return dados
        self.fail("o painel perdeu o gráfico %r" % trecho)

    def _pivo(self, nome):
        for p in self.planilha["pivots"].values():
            if p["name"] == nome:
                return p
        self.fail("o painel perdeu o pivô %r" % nome)

    def _soma(self, model, dominio, campo, extra):
        [(total,)] = self.env[model]._read_group(
            list(dominio) + extra, aggregates=[campo + ":sum"])
        return total or 0.0

    # -- o de cima: pedidos ------------------------------------------------
    def _pedido(self, confirmar=True):
        pedido = self.env["sale.order"].create({
            "partner_id": self.cliente.id,
            "order_line": [(0, 0, {"product_id": self.livro.id,
                                   "product_uom_qty": 2})],
        })
        if confirmar:
            pedido.action_confirm()
        return pedido

    def test_o_grafico_de_cima_soma_pedido_confirmado_e_nao_cotacao(self):
        confirmado = self._pedido()
        cotacao = self._pedido(confirmar=False)
        self.env.flush_all()
        grafico = self._grafico("Vendido pelos pedidos")
        self.assertEqual(grafico["metaData"]["resModel"], "sale.report")
        self.assertEqual(grafico["metaData"]["measure"], "price_subtotal")
        self.assertIn("team_id", grafico["metaData"]["groupBy"],
                      "o canal de venda tem de ser eixo do gráfico")
        dominio = grafico["searchParams"]["domain"]
        soma = self._soma("sale.report", dominio, "price_subtotal",
                          [("partner_id", "=", self.cliente.id)])
        self.assertEqual(soma, confirmado.amount_untaxed)
        self.assertNotEqual(soma, confirmado.amount_untaxed + cotacao.amount_untaxed,
                            "a cotação entrou no vendido")

    def test_o_dia_do_pedido_e_no_fuso_de_quem_olha(self):
        """23h de 31/08 em São Paulo é 02h de 01/09 em UTC: o `date` do núcleo
        diria setembro; o dia do pedido diz agosto, que é o que o vendedor viu."""
        pedido = self._pedido()
        pedido.date_order = "2026-09-01 02:00:00"
        self.env.flush_all()
        R = self.env["sale.report"].with_context(tz="America/Sao_Paulo")
        [linha] = R.search([("name", "=", pedido.name)])
        self.assertEqual(str(linha.order_date), "2026-08-31")
        # O cache do ORM é da transação, não do contexto: sem invalidar, a
        # segunda leitura devolveria o dia calculado para São Paulo.
        self.env.invalidate_all()
        [linha] = R.with_context(tz="UTC").search([("name", "=", pedido.name)])
        self.assertEqual(str(linha.order_date), "2026-09-01")

    def test_a_tabela_dos_pedidos_traz_vendido_faturado_e_a_faturar(self):
        pivo = self._pivo("Pedidos por mês")
        medidas = [m["fieldName"] for m in pivo["measures"]]
        self.assertEqual(medidas, ["price_subtotal", "untaxed_amount_invoiced",
                                   "untaxed_amount_to_invoice"])
        self.assertEqual(pivo["rows"][0]["fieldName"], "order_date",
                         "o eixo dos pedidos é o DIA do pedido, no fuso de quem olha")

    # -- o de baixo: notas -------------------------------------------------
    def _xml(self, valor, direcao="out", cfop=None, cancelada=False, frete=0.0):
        """A nota com um item: o painel soma o LÍQUIDO DOS ITENS, não o
        total da DANFE (que carrega o frete) -- a régua do Painel de Notas."""
        nota = self.env["nfe.xml.panel"].create({
            "file": base64.b64encode(b"<nfe/>"), "file_name": "nota.xml",
            "partner_id": self.cliente.id,
            "company_id": self.env.company.id,
            "nfe_direction": direcao,
            "cfop_id": (cfop or self.cfop_venda).id,
            "danfe_value": valor + frete,
            "file_create_date": "2026-09-06",
            "is_cancelled": cancelada,
        })
        self.env["nfe.xml.items"].create({
            "soc_xml_id": nota.id, "ks_product_name": "Livro do painel",
            "ks_product_qty": 1, "ks_price": valor, "net_price": valor})
        return nota

    def test_o_grafico_de_baixo_soma_a_nota_emitida_por_nos(self):
        self._xml(100.0, frete=15.0)                       # a venda com nota; o frete fica fora
        self._xml(70.0, direcao="internal")                # intercompany: receita de quem emitiu
        self._xml(999.0, direcao="in")                     # nota do FORNECEDOR, CFOP 5101 dele
        self._xml(500.0, cancelada=True)                   # cancelada
        self._xml(300.0, cfop=self.cfop_remessa)           # remessa de consignação
        self.env.flush_all()
        grafico = self._grafico("Vendido com nota")
        self.assertEqual(grafico["metaData"]["resModel"], "nfe.xml.panel")
        self.assertEqual(grafico["metaData"]["measure"], "net_value",
                         "o lado da nota soma o líquido dos itens, sem frete")
        self.assertIn("file_create_date:month", grafico["metaData"]["groupBy"],
                      "o eixo das notas é a DATA DA NOTA")
        self.assertIn("team_id", grafico["metaData"]["groupBy"])
        soma = self._soma("nfe.xml.panel", grafico["searchParams"]["domain"],
                          "net_value", [("partner_id", "=", self.cliente.id)])
        self.assertEqual(soma, 170.0)
        pivo = self._pivo("Notas por mês")
        self.assertEqual([m["fieldName"] for m in pivo["measures"]],
                         ["net_value", "book_qty", "__count"],
                         "a tabela das notas traz vendido, livros e notas")

    def test_a_linha_do_faturamento_e_a_evolucao_das_faturas(self):
        """O primeiro gráfico é uma linha, como o "Vendas mensais" do core,
        com o mesmo recorte e a mesma medida do cartão Faturas."""
        [linha] = [f["data"] for f in self.planilha["sheets"][0]["figures"]
                   if f["data"]["type"] == "odoo_line" and f["data"]["title"]["text"] == "Faturamento"]
        self.assertEqual(linha["metaData"]["resModel"], "nfe.xml.panel")
        self.assertEqual(linha["metaData"]["measure"], "net_value")
        self.assertEqual(linha["searchParams"]["domain"], self._pivo("Notas por mês")["domain"])
        self.assertTrue(linha["fillArea"])

    def test_todo_cartao_compara_com_o_periodo_anterior(self):
        """"↑ x% desde o período anterior", como nos cartões do core: o agora
        vem dos pivôs do período, o anterior dos mesmos pivôs com offset -1
        -- mesmo recorte, só o tempo muda."""
        cartoes = [f["data"] for f in self.planilha["sheets"][0]["figures"]
                   if f["data"]["type"] == "scorecard"]
        for c in cartoes:
            self.assertEqual(c["baselineMode"], "percentage", c["title"]["text"])
            self.assertTrue(c["baseline"].startswith("Dados!D"), c["title"]["text"])
        pivos = self.planilha["pivots"]
        [periodo] = [f["id"] for f in self.planilha["globalFilters"] if f["type"] == "date"]
        for agora, antes in (("1", "4"), ("2", "5"), ("3", "6")):
            self.assertEqual(pivos[agora]["domain"], pivos[antes]["domain"])
            self.assertEqual(pivos[antes]["fieldMatching"][periodo]["offset"], -1)
            self.assertEqual(pivos[agora]["fieldMatching"][periodo]["offset"], 0)

    def test_os_dois_pivos_usam_o_mesmo_recorte_dos_graficos(self):
        """Os cartões leem os pivôs; os gráficos, o searchParams. Um recorte
        que mude num lado e não no outro faria o cartão desmentir o gráfico."""
        self.assertEqual(self._pivo("Pedidos por mês")["domain"],
                         self._grafico("Vendido pelos pedidos")["searchParams"]["domain"])
        self.assertEqual(self._pivo("Notas por mês")["domain"],
                         self._grafico("Vendido com nota")["searchParams"]["domain"])

    def test_o_periodo_alcanca_as_quatro_fontes(self):
        """Um filtro só move os dois relógios: pedido pela data do pedido,
        nota pela data da nota."""
        [filtro] = [f for f in self.planilha["globalFilters"] if f["type"] == "date"]
        self.assertEqual({f["label"] for f in self.planilha["globalFilters"]},
                         {"Período", "Cliente", "Canal de vendas"},
                         "os filtros do core que servem aos dois relógios")
        for pivo in self.planilha["pivots"].values():
            self.assertIn(filtro["id"], pivo["fieldMatching"])
        cadeias = {self._grafico("Vendido pelos pedidos")["fieldMatching"][filtro["id"]]["chain"],
                   self._grafico("Vendido com nota")["fieldMatching"][filtro["id"]]["chain"]}
        self.assertEqual(cadeias, {"order_date", "file_create_date"})

    # -- a tela ------------------------------------------------------------
    # -- os filtros da lista que o cartão abre -----------------------------
    def _filtro(self, nome):
        """O domínio do filtro como a tela o recebe, com a view herdada aplicada."""
        from lxml import etree
        arch = self.env["nfe.xml.panel"].get_view(view_type="search")["arch"]
        achados = etree.fromstring(arch).xpath("//filter[@name='%s']" % nome)
        if not achados:
            self.fail("a busca das notas perdeu o filtro %r" % nome)
        return safe_eval(achados[0].get("domain"))

    def test_a_lista_separa_sem_fatura_de_fatura_sem_pedido(self):
        """"Notas sem fatura nenhuma é muito estranho" -- o cartão soma dois
        casos que pedem remédios diferentes, e a lista tem de separá-los sem
        ler linha por linha: sem fatura, fatura sem pedido, com pedido."""
        pedido = self._pedido()
        pedido.order_line.qty_delivered = 2
        ligada = pedido._create_invoices()
        solta = self.env["account.move"].create({
            "move_type": "out_invoice", "partner_id": self.cliente.id,
            "invoice_line_ids": [(0, 0, {"product_id": self.livro.id,
                                         "quantity": 1, "price_unit": 90.0})]})
        com_pedido = self._xml(100.0)
        com_pedido.invoice_id = ligada
        sem_pedido = self._xml(90.0)
        sem_pedido.invoice_id = solta
        sem_fatura = self._xml(60.0)
        self.env.flush_all()
        minhas = [("partner_id", "=", self.cliente.id)]
        Nota = self.env["nfe.xml.panel"]
        self.assertEqual(Nota.search(self._filtro("sem_fatura") + minhas), sem_fatura)
        self.assertEqual(Nota.search(self._filtro("fatura_sem_pedido") + minhas), sem_pedido)
        self.assertEqual(Nota.search(self._filtro("com_pedido") + minhas), com_pedido)
        # Os dois primeiros filtros, juntos, são exatamente o cartão.
        acao = self.env.ref("liber_sales_dashboard.action_notas_sem_pedido")
        self.assertEqual(Nota.search(safe_eval(acao.domain) + minhas),
                         sem_fatura | sem_pedido)

    def test_e_o_proprio_painel_de_vendas_do_core(self):
        """Uma entrada só: o conteúdo mora no registro do core, com o nome,
        o grupo e a posição dele -- não há um segundo "Sales" na lateral."""
        self.assertTrue(self.painel.is_published)
        self.assertEqual(self.painel.dashboard_group_id, self.env.ref(
            "spreadsheet_dashboard.spreadsheet_dashboard_group_sales"))
        self.assertIn("nfe.xml.panel", self.painel.main_data_model_ids.mapped("model"))
        self.assertFalse(self.env["spreadsheet.dashboard"].search_count(
            [("id", "!=", self.painel.id),
             ("dashboard_group_id", "=", self.painel.dashboard_group_id.id),
             ("name", "ilike", "notes")]), "sobrou um painel Vendas × Notas ao lado")

    def test_quem_nao_e_do_comercial_nao_ve_o_painel(self):
        de_fora = self.env["res.users"].create({
            "name": "Sem vendas", "login": "painel_vendas_de_fora",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            self.painel.with_user(de_fora).read(["name"])

    # -- clicável para auditoria -------------------------------------------
    def test_todo_cartao_e_grafico_abre_uma_lista_que_existe(self):
        """Cada número do painel leva à lista de onde saiu. Um menu que não
        existe (módulo renomeado, xmlid trocado) deixaria o clique mudo."""
        refs = self.planilha["chartOdooMenusReferences"]
        figuras = [f["id"] for f in self.planilha["sheets"][0]["figures"]]
        self.assertEqual(set(refs), set(figuras),
                         "todo cartão e gráfico tem de ser clicável")
        for xmlid in refs.values():
            self.assertTrue(self.env.ref(xmlid, raise_if_not_found=False),
                            "o menu %s não existe" % xmlid)

    def test_os_cinco_cartoes_na_ordem_e_com_a_conta_do_dono(self):
        """Faturas · Pedidos · Pedidos fechados · Pedidos abertos · Faturas sem
        pedido -- nomes, ordem e contas ditados em 06/09/2026. "Pedidos
        abertos" é Pedidos − Pedidos fechados (não o "a faturar" do
        contador, que pode ser negativo); "Faturas sem pedido" é Faturas −
        Pedidos fechados."""
        cartoes = sorted(
            [f for f in self.planilha["sheets"][0]["figures"] if f["data"]["type"] == "scorecard"],
            key=lambda f: f["offset"]["x"])
        self.assertEqual([c["data"]["title"]["text"] for c in cartoes],
                         ["Faturas", "Pedidos", "Pedidos fechados",
                          "Pedidos abertos", "Faturas sem pedido"])
        dados = self.planilha["sheets"][1]["cells"]
        self.assertIn("PIVOT.VALUE(2,\"net_value\")", dados["B1"])
        self.assertIn("PIVOT.VALUE(1,\"price_subtotal\")", dados["B2"])
        self.assertIn("PIVOT.VALUE(1,\"untaxed_amount_invoiced\")", dados["B3"])
        self.assertEqual(dados["B4"], "=B2-B3")
        self.assertIn("PIVOT.VALUE(3,\"net_value\")", dados["B5"],
                      "Faturas sem pedido é a soma de uma lista, não uma conta")
        self.assertEqual([c["data"]["background"] for c in cartoes],
                         ["#ccccff", "#e6e6ff", "#e6e6ff", "#e6e6ff", "#ccccff"],
                         "duas famílias em lavanda: nota fiscal mais forte, pedido mais claro")

    # -- o cartão que é uma lista -------------------------------------------
    def test_faturas_sem_pedido_e_a_soma_da_lista_que_o_clique_abre(self):
        """O número de fora tem de ser o de dentro: o pivô do cartão e a ação
        do menu usam o mesmo recorte, e o recorte sabe distinguir a nota cuja
        fatura está ligada a um pedido da que não está."""
        pivo = self._pivo("Notas sem pedido")
        acao = self.env.ref("liber_sales_dashboard.action_notas_sem_pedido")
        normal = lambda d: json.loads(json.dumps([list(c) if isinstance(c, (list, tuple)) else c for c in d]))
        self.assertEqual(normal(pivo["domain"]), normal(eval(acao.domain)),
                         "cartão e lista com recortes diferentes")
        # Três notas: com fatura ligada a pedido (fora), com fatura solta
        # (dentro), sem fatura (dentro).
        pedido = self._pedido()
        pedido.order_line.qty_delivered = 2
        fatura_ligada = pedido._create_invoices()
        fatura_ligada.action_post()
        fatura_solta = self.env["account.move"].create({
            "move_type": "out_invoice", "partner_id": self.cliente.id,
            "invoice_line_ids": [(0, 0, {"product_id": self.livro.id,
                                         "quantity": 1, "price_unit": 100.0})]})
        self._xml(200.0).invoice_id = fatura_ligada
        self._xml(100.0).invoice_id = fatura_solta
        self._xml(50.0)
        self.env.flush_all()
        soma = self._soma("nfe.xml.panel", pivo["domain"], "net_value",
                          [("partner_id", "=", self.cliente.id)])
        self.assertEqual(soma, 150.0, "só a solta e a sem fatura entram")
        self.assertTrue(self.env.ref("liber_sales_dashboard.menu_notas_sem_pedido").parent_id
                        .parent_id == self.env.ref("sale.sale_menu_root"),
                        "a lista mora em Vendas, onde o gerente chega")
