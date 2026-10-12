# -*- coding: utf-8 -*-
from lxml import etree

from odoo.tests.common import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


# `post_install` pelo mesmo motivo do test_unique_royalty_line: criar
# `res.partner` antes do `account` carregar bate no NOT NULL de autopost_bills.
@tagged("post_install", "-at_install")
class TestNoBeneficiaryFilter(TransactionCase):
    """O filtro provisório "Sem beneficiário" (06/10/2026) pega o contrato que
    entrou da planilha de Gestão de Contratos sem linha de royalty -- e solta
    assim que alguém preencher o beneficiário."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = cls.env["res.partner"].create({"name": "Beneficiária Teste"})
        cls.work = cls.env["product.template"].create({"name": "Obra Teste"})
        cls.Contract = cls.env["edlab.contract"]
        cls.blank = cls.Contract.create({
            "company_id": cls.env.company.id,
            "location": "FULANO_OBRA_CONTRATO.pdf",
        })
        cls.filled = cls.Contract.create({
            "company_id": cls.env.company.id,
            "royalty_line_ids": [(0, 0, {
                "partner_id": cls.author.id,
                "product_id": cls.work.id,
            })],
        })

    def _filter_domain(self):
        """Lê o domínio do filtro na search view de verdade, para o teste
        provar a tela e não uma cópia do domínio."""
        view = self.env.ref("liber_copyright_contracts.view_edlab_contract_search")
        arch = self.Contract.get_view(view.id, "search")["arch"]
        node = etree.fromstring(arch).xpath("//filter[@name='no_beneficiary']")
        self.assertEqual(len(node), 1, "o filtro 'no_beneficiary' sumiu da search view")
        return safe_eval(node[0].get("domain"))

    def test_blank_contract_is_listed(self):
        """Caminho feliz: contrato sem linha aparece; o preenchido não."""
        found = self.Contract.search(self._filter_domain())
        self.assertIn(self.blank, found)
        self.assertNotIn(self.filled, found)

    def test_leaves_filter_when_beneficiary_is_set(self):
        """Edge: ao ganhar a linha com beneficiário, o contrato sai do filtro."""
        self.blank.write({"royalty_line_ids": [(0, 0, {
            "partner_id": self.author.id,
            "product_id": self.work.id,
        })]})
        self.env.flush_all()
        self.assertNotIn(self.blank, self.Contract.search(self._filter_domain()))

    def test_line_still_requires_beneficiary(self):
        """Erro: a linha de royalty continua exigindo beneficiário -- o
        'em branco' é a ausência da linha, não uma linha com partner vazio."""
        with self.assertRaises(Exception), self.cr.savepoint():
            self.env["edlab.contract.royalty.line"].create({
                "contract_id": self.blank.id,
                "product_id": self.work.id,
            })
