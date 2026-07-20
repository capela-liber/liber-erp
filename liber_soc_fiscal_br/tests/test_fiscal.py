# -*- coding: utf-8 -*-
"""Tests for the fiscal layer: the consignment shelf is a NON-valued internal
location (so WH->shelf posts as a valued out), and the CFOP must agree with
the document kind."""
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "soc_fiscal")
class TestFiscalBr(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1)
        cls.product = cls.env["product.product"].create({
            "name": "Quincas Borba", "type": "consu",
            "is_storable": True, "list_price": 40.0})

    def _agreement(self, name):
        partner = self.env["res.partner"].create({
            "name": name, "is_company": True})
        agr = self.env["consignment.agreement"].create({
            "partner_id": partner.id,
            "company_id": self.company.id,
            "date_start": fields.Date.today(),
        })
        agr.action_activate()
        return agr

    def _cfop(self, code, kind):
        return self.env["nfe.cfop"].create({
            "code": code,
            "name": "CFOP %s (%s)" % (code, kind),
            "document_kind": kind,
        })

    def test_shelf_is_not_valued(self):
        """The single lever of the module: shelves opt out of valuation."""
        agr = self._agreement("Livraria Fiscal A")
        self.assertFalse(agr.location_id._should_be_valued())
        self.assertTrue(self.warehouse.lot_stock_id._should_be_valued(),
                        "a normal internal location must keep valuation")

    def test_shelf_gets_valuation_account_on_creation(self):
        account = self.env["account.account"].create({
            "code": "115999", "name": "Estoque em Consignação (teste)",
            "account_type": "asset_current",
        })
        self.company.consignment_stock_account_id = account
        agr = self._agreement("Livraria Fiscal B")
        self.assertEqual(agr.location_id.valuation_account_id, account)

    def test_wire_backfills_existing_shelves(self):
        agr = self._agreement("Livraria Fiscal C")
        agr.location_id.valuation_account_id = False
        account = self.env["account.account"].create({
            "code": "115998", "name": "Estoque em Consignação (backfill)",
            "account_type": "asset_current",
        })
        self.company.consignment_stock_account_id = account
        self.company.action_wire_consignment_shelves()
        self.assertEqual(agr.location_id.valuation_account_id, account)

    def test_cfop_must_match_document_kind(self):
        agr = self._agreement("Livraria Fiscal D")
        consignment_cfop = self._cfop("5917", "consignment")
        bonus_cfop = self._cfop("5910", "bonus")

        # consignment CFOP on a plain order -> rejected
        with self.assertRaises(UserError):
            self.env["sale.order"].create({
                "partner_id": agr.partner_id.id,
                "is_consignment": False,
                "cfop_id": consignment_cfop.id,
                "order_line": [(0, 0, {
                    "product_id": self.product.id,
                    "product_uom_qty": 1,
                })],
            })
        # bonus CFOP on a Pedido C -> rejected
        with self.assertRaises(UserError):
            self.env["sale.order"].create({
                "partner_id": agr.partner_id.id,
                "is_consignment": True,
                "consignment_type": "opening",
                "cfop_id": bonus_cfop.id,
                "order_line": [(0, 0, {
                    "product_id": self.product.id,
                    "product_uom_qty": 1,
                })],
            })
        # matching combo passes
        order = self.env["sale.order"].create({
            "partner_id": agr.partner_id.id,
            "is_consignment": True,
            "consignment_type": "opening",
            "cfop_id": consignment_cfop.id,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": 1,
            })],
        })
        self.assertTrue(order)

    def test_bonus_order_never_invoices(self):
        agr = self._agreement("Livraria Fiscal E")
        bonus_cfop = self._cfop("5911", "bonus")
        order = self.env["sale.order"].create({
            "partner_id": agr.partner_id.id,
            "cfop_id": bonus_cfop.id,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": 1,
            })],
        })
        order.action_confirm()
        with self.assertRaises(UserError):
            order._create_invoices()


# Campos fiscais declarados que NENHUM código lê ainda, com o motivo de cada um.
# A lista existe para o teste abaixo pegar campo burro NOVO sem travar em cima
# de dívida já documentada -- e ele também falha quando um waiver fica OBSOLETO,
# para a lista não virar cemitério.
DEAD_CONFIG_WAIVERS = {
    # consignment_shipment_fiscal_position_id saiu daqui em 19/07/2026: a nota
    # de remessa do Pedido C (nfe_remessa) passou a consumi-lo -- exatamente o
    # caso "waiver obsoleto" que este teste existe para flagrar.
    'consignment_return_fiscal_position_id':
        "a devolução é movimento de estoque, não fatura -- não cria documento "
        "contábil que uma posição fiscal pudesse reger.",
    'consignment_shipment_cfop_in_id': "nada neste repo emite XML.",
    'consignment_shipment_cfop_out_id': "nada neste repo emite XML.",
    'consignment_sale_cfop_in_id': "nada neste repo emite XML.",
    'consignment_sale_cfop_out_id': "nada neste repo emite XML.",
    'consignment_return_cfop_in_id': "nada neste repo emite XML.",
    'consignment_return_cfop_out_id': "nada neste repo emite XML.",
}


@tagged("post_install", "-at_install", "soc_fiscal")
class TestConsignmentFiscalPosition(TransactionCase):
    """A posição fiscal do acerto vem da OPERAÇÃO, não do cliente."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.product = cls.env["product.product"].create({
            "name": "Grande Sertão", "type": "consu",
            "is_storable": True, "list_price": 50.0})
        cls.fp_venda = cls.env["account.fiscal.position"].create({
            "name": "Venda comum", "company_id": cls.company.id})
        cls.fp_consig = cls.env["account.fiscal.position"].create({
            "name": "Consignação", "company_id": cls.company.id})

    def _settlement(self):
        partner = self.env["res.partner"].create({
            "name": "Livraria da Esquina", "is_company": True})
        # A posição fiscal DO CLIENTE -- a errada para esta operação.
        partner.property_account_position_id = self.fp_venda
        agr = self.env["consignment.agreement"].create({
            "partner_id": partner.id, "company_id": self.company.id,
            "date_start": fields.Date.today()})
        agr.action_activate()
        st = self.env["consignment.settlement"].create({
            "partner_id": partner.id, "company_id": self.company.id})
        line = self.env["consignment.settlement.line"].create({
            "settlement_id": st.id, "product_id": self.product.id,
            "qty_reported": 2, "price_unit": 50.0})
        return st, line

    def test_operation_wins_over_customer(self):
        """A MESMA livraria recebe consignação (5917) e compra em firme (5102).

        O parceiro tem UM campo de posição fiscal (property_account_position_id),
        então ele não codifica as duas -- e o padrão do Odoo, que deriva do
        parceiro, resolveria o eixo errado, em silêncio.
        """
        self.company.consignment_sale_fiscal_position_id = self.fp_consig
        st, line = self._settlement()
        order = st._create_sale_order(line)
        self.assertEqual(
            order.fiscal_position_id, self.fp_consig,
            "o acerto pegou a posição fiscal do CLIENTE (%s) em vez da da "
            "OPERAÇÃO (%s) -- é assim que uma nota sai errada sem ninguém ver"
            % (order.fiscal_position_id.name, self.fp_consig.name))

    def test_unconfigured_company_falls_back_and_does_not_explode(self):
        """Configuração em branco não pode parar o acerto no meio do action_run."""
        self.company.consignment_sale_fiscal_position_id = False
        st, line = self._settlement()
        order = st._create_sale_order(line)
        self.assertEqual(order.fiscal_position_id, self.fp_venda)

    def test_locked_for_ordinary_user_open_for_the_fiscal_group(self):
        """Meio-termo: trava para quem opera, saída para quem responde fiscal."""
        self.company.consignment_sale_fiscal_position_id = self.fp_consig
        st, line = self._settlement()
        order = st._create_sale_order(line)

        comum = self.env["res.users"].create({
            "name": "Gerente de vendas", "login": "operadora_fiscal_test",
            "group_ids": [(6, 0, [
                self.env.ref("sales_team.group_sale_manager").id])]})
        self.assertTrue(
            order.with_user(comum).consignment_fiscal_locked,
            "nem o gerente de VENDAS deve trocar a posição fiscal do acerto")

        gerente = self.env["res.users"].create({
            "name": "Fiscal", "login": "fiscal_test",
            "group_ids": [(6, 0, [
                self.env.ref("sales_team.group_sale_manager").id,
                self.env.ref("account.group_account_manager").id])]})
        self.assertFalse(
            order.with_user(gerente).consignment_fiscal_locked,
            "a exceção legítima (regime especial, ST) viraria chamado para o dev")

    def test_plain_sale_order_is_not_locked(self):
        """A trava é da operação de consignação, não de todo pedido da casa."""
        partner = self.env["res.partner"].create({"name": "Cliente avulso"})
        order = self.env["sale.order"].create({"partner_id": partner.id})
        self.assertFalse(order.consignment_fiscal_locked)

    def test_no_dumb_config_fields(self):
        """Alerta quando criamos campo de configuração que ninguém lê.

        Configuração morta é pior que configuração nenhuma: ela mente para quem
        preenche. Foi assim que as posições fiscais de consignação passaram
        despercebidas -- declaradas, na tela, e sem consumidor.
        """
        import glob
        import os
        import re
        from odoo.modules import get_module_path

        # O próprio arquivo de teste cita os nomes (nos waivers), então ele fica
        # de fora da varredura -- senão todo campo pareceria vivo.
        code = "\n".join(
            open(f, encoding='utf-8').read()
            for f in glob.glob(os.path.join(get_module_path('liber_soc_fiscal_br'),
                                            '**', '*.py'), recursive=True)
            if os.sep + 'tests' + os.sep not in f)

        dead, revived = [], []
        for name, field in self.env['res.company']._fields.items():
            if 'liber_soc_fiscal_br' not in (getattr(field, '_modules', None) or ()):
                continue
            body = [ln for ln in code.split('\n')
                    if not re.match(r'\s*%s\s*=\s*fields\.' % re.escape(name), ln)
                    and not ('related=' in ln
                             and "company_id.%s" % name in ln)]
            lido = any(name in ln for ln in body)
            if not lido and name not in DEAD_CONFIG_WAIVERS:
                dead.append(name)
            if lido and name in DEAD_CONFIG_WAIVERS:
                revived.append(name)

        self.assertFalse(dead, (
            "configuração que ninguém lê (campos burros): %s\n"
            "Ou consome no código, ou apaga, ou põe em DEAD_CONFIG_WAIVERS com "
            "o motivo. Campo que promete e não cumpre é armadilha." % dead))
        self.assertFalse(revived, (
            "estes campos já são lidos e continuam na lista de waivers: %s\n"
            "Tire-os da lista para ela não virar cemitério." % revived))
