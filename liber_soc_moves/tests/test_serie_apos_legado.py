# -*- coding: utf-8 -*-
"""A série nova nasce depois do maior nome já usado (o acidente de 21/08).

O histórico legado entra no prod com pickings nomeados direto, sem passar por
ir.sequence; a sequence criada no primeiro "Liberar para Logística" começava
em 1 e morria na name_uniq do stock.picking — e o rollback desfazia o tipo e
a sequence, deixando o erro permanente. Estes testes cravam o conserto:
`_consignment_series_start` lê o maior sufixo numérico da série na empresa e
a sequence nasce um adiante.
"""
from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "soc_moves")
class TestSerieAposLegado(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1)
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.product = cls.env["product.product"].create({
            "name": "Quincas Borba", "type": "consu",
            "is_storable": True, "list_price": 50.0})
        cls.partner = cls.env["res.partner"].create({
            "name": "Livraria do Legado", "is_company": True})
        cls.agreement = cls.env["consignment.agreement"].create({
            "partner_id": cls.partner.id,
            "company_id": cls.company.id,
            "date_start": fields.Date.today(),
        })
        cls.agreement.action_activate()

    def _picking_legado(self, name, company=None):
        """Um picking como o import do legado o deixa: nome escrito direto,
        sem sacar de sequence nenhuma."""
        company = company or self.company
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", company.id)], limit=1)
        return self.env["stock.picking"].create({
            "name": name,
            "picking_type_id": warehouse.int_type_id.id,
            "company_id": company.id,
            "location_id": warehouse.lot_stock_id.id,
            "location_dest_id": warehouse.lot_stock_id.id,
        })

    def test_liberar_depois_do_legado_nao_colide(self):
        # O cenário do prod: nomes COM/IN já existem, o tipo de retorno não.
        year = fields.Date.today().year
        self._picking_legado("COM/IN/%s/00777" % year)
        self.company.sudo().consignment_return_operation_type_id = False

        self.env["stock.quant"]._update_available_quantity(
            self.product, self.agreement.location_id, 10)
        move = self.env["consignment.move"].create({
            "partner_id": self.partner.id,
            "move_kind": "return",
            "line_ids": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": 4,
            })],
        })
        move.action_confirm()
        # Antes do conserto este release morria na name_uniq (a sequence nova
        # dava COM/IN/ano/00001, nome que o legado pode já ter usado).
        move.action_release()
        self.assertEqual(move.state, "confirmed")
        self.assertEqual(move.picking_id.name, "COM/IN/%s/00778" % year,
                         "a série deve continuar um adiante do legado")

    def test_serie_virgem_comeca_em_um(self):
        # Prefixo que ninguém usou: nada a pular.
        self.assertEqual(
            self.company._consignment_series_start("XX/TESTE/%(year)s/"), 1)
        # Sufixo não numérico na série não é número e não conta.
        self._picking_legado("XX/TESTE/solto")
        self.assertEqual(
            self.company._consignment_series_start("XX/TESTE/%(year)s/"), 1)

    def test_legado_de_outra_empresa_nao_conta(self):
        # A name_uniq é por empresa; o ponto de partida também tem de ser.
        outra = self.env["stock.warehouse"].search(
            [("company_id", "!=", self.company.id)], limit=1).company_id
        if not outra:
            self.skipTest("base sem segunda empresa com armazém")
        self._picking_legado("XX/ISOLA/2026/00500", company=outra)
        self.assertEqual(
            self.company._consignment_series_start("XX/ISOLA/%(year)s/"), 1)
        self.assertEqual(
            outra._consignment_series_start("XX/ISOLA/%(year)s/"), 501)

    def test_serie_start_exige_uma_empresa(self):
        # Contrato do método: uma empresa por vez (o número é por empresa).
        with self.assertRaises(ValueError):
            (self.company | self.env["res.company"].search(
                [("id", "!=", self.company.id)], limit=1)
             )._consignment_series_start("XX/TESTE/%(year)s/")
