# -*- coding: utf-8 -*-
"""O literal da SEFAZ nunca vira nome de parceiro.

Nota emitida em ambiente de homologação sai da SEFAZ com o destinatário
trocado por "NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL".
Em agosto de 2026 um reprocessamento gravou a frase como NOME de nove
parceiros reais -- três filiais da Amazon, a Eunice Livros e o dono da casa.
O CNPJ ficou certo; o rótulo virou a frase, e 3.581 notas passaram a ter um
cliente que ninguém acha procurando pelo nome.

A trava mora no modelo, e não em quem importa: o nome pode chegar pelo XML,
pela migração, pelo Olist ou pela Focus, e todos passam por `write`. Aqui se
prova a regra pelos dois lados e pela borda -- um nome legítimo que contém a
palavra "homologação" (uma consultoria, por exemplo) não pode ser recusado.
"""
from odoo.tests import TransactionCase, tagged

LITERAL = "NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"


@tagged("post_install", "-at_install", "nfe_xml")
class TestLiteralDeHomologacao(TransactionCase):

    def _parceiro(self, **extra):
        vals = {"name": "Livraria Vera", "vat": "43.791.310/0001-99"}
        vals.update(extra)
        return self.env["res.partner"].create(vals)

    # -- o write: o caso dos nove -------------------------------------------
    def test_write_com_o_literal_mantem_o_nome(self):
        p = self._parceiro()
        p.write({"name": LITERAL})
        self.assertEqual(p.name, "Livraria Vera",
                         "o literal da SEFAZ sobrescreveu um nome real")

    def test_write_com_o_literal_na_razao_social_mantem(self):
        p = self._parceiro(legal_name="LIVRARIA VERA LTDA")
        p.write({"legal_name": LITERAL})
        self.assertEqual(p.legal_name, "LIVRARIA VERA LTDA")

    def test_o_resto_do_write_continua_valendo(self):
        """Descartar o nome não pode engolir os outros campos do mesmo write."""
        p = self._parceiro()
        p.write({"name": LITERAL, "email": "vera@livraria.br"})
        self.assertEqual(p.name, "Livraria Vera")
        self.assertEqual(p.email, "vera@livraria.br")

    # -- o create: nascer com o literal ------------------------------------
    def test_create_com_o_literal_nasce_com_o_documento(self):
        p = self.env["res.partner"].create({"name": LITERAL, "vat": "15436940000367"})
        self.assertNotIn("HOMOLOGA", p.name.upper())
        self.assertEqual(p.name, "15.436.940/0003-67",
                         "sem outro nome, o documento é o único que se sabe verdadeiro")

    # -- variações do literal ----------------------------------------------
    def test_pega_a_grafia_com_acento_e_sem_hifen(self):
        p = self._parceiro()
        p.write({"name": "NFE EMITIDA EM AMBIENTE DE HOMOLOGAÇÃO"})
        self.assertEqual(p.name, "Livraria Vera")

    # -- a borda: quem tem 'homologação' no nome de verdade -----------------
    def test_nome_legitimo_com_a_palavra_passa(self):
        p = self._parceiro(name="Consultoria em Homologação Fiscal Ltda")
        self.assertEqual(p.name, "Consultoria em Homologação Fiscal Ltda")
        p.write({"name": "Homologação & Cia"})
        self.assertEqual(p.name, "Homologação & Cia")
