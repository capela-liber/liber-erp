# -*- coding: utf-8 -*-
"""O nome que a nota declara: razão social quando a ficha a tem.

O xNome do destinatário é o nome sob o qual o CNPJ está registrado. Antes do
`legal_name` a nota saía com o `name` cru -- e uma ficha rebatizada de
"Travessa Botafogo" mandava o apelido para a SEFAZ. No emitente era pior:
`nome_emitente` e `nome_fantasia_emitente` eram a MESMA string, porque
`company.name` é related de `partner.name`.
"""
from odoo.tests import TransactionCase, tagged

RAZAO = "LIVRARIA DA TRAVESSA LTDA"
APELIDO = "Travessa Botafogo"
CNPJ = "31.004.013/0021-06"


@tagged("post_install", "-at_install")
class TestNomeFiscal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]

    def test_destinatario_usa_razao_social(self):
        partner = self.Partner.create({
            "name": APELIDO, "legal_name": RAZAO, "vat": CNPJ})
        self.assertEqual(partner._focus_destinatario_data()["nome"], RAZAO)

    def test_destinatario_sem_razao_cai_no_nome(self):
        """Ficha sem legal_name emite exatamente como sempre emitiu."""
        partner = self.Partner.create({"name": APELIDO, "vat": CNPJ})
        self.assertEqual(partner._focus_destinatario_data()["nome"], APELIDO)

    def test_transportador_usa_razao_social(self):
        partner = self.Partner.create({
            "name": "Transportes Zé", "legal_name": "ZE TRANSPORTES LTDA",
            "vat": "04.354.383/0001-06"})
        self.assertEqual(
            partner._focus_transportador_data()["nome"], "ZE TRANSPORTES LTDA")

    def test_emitente_distingue_razao_de_fantasia(self):
        # Empresa reaproveitada do banco de teste: criar res.company com o
        # `account` instalado esbarra no fiscalyear (regra da casa).
        company = self.env.company
        company.vat = "35.288.052/0001-90"
        company.partner_id.legal_name = "EDLAB PRESS EDITORA LTDA"
        company.partner_id.name = "Edlab Press"

        emitente = company._focus_emitente_data()

        self.assertEqual(emitente["nome"], "EDLAB PRESS EDITORA LTDA")
        self.assertEqual(emitente["nome_fantasia"], "Edlab Press")

    def test_emitente_sem_razao_mantem_o_de_sempre(self):
        company = self.env.company
        company.vat = "35.288.052/0001-90"
        company.partner_id.legal_name = False

        emitente = company._focus_emitente_data()

        self.assertEqual(emitente["nome"], company.name,
                         "sem legal_name o payload não pode mudar em nada")
