# -*- coding: utf-8 -*-
"""A prateleira nasce COM A CONTA e sem Inventário.

Terceiro dia do mesmo bloqueio, e a terceira frase diferente na mesma caixa.

    26/08  "Você não tem permissões para CRIAR registros de 'Locais de
            inventário'"  -> a criação da prateleira foi para sudo, no
            liber_soc_agreements.
    27/08  "Você não tem permissão para MODIFICAR registros de 'Locais de
            inventário'"  -> era este módulo, carimbando a conta de estoque
            em consignação em cima do local recém-criado.

O conserto de 26/08 passou ao largo porque este é outro módulo e outra
operação: criar deixou de pedir Inventário, escrever continuava pedindo.

E o teste que existia (`test_shelf_gets_valuation_account_on_creation`, no
test_fiscal.py) não tinha como pegar, por dois motivos que se somam:

1. Ele roda como ADMIN, que passa em tudo -- é a regra de 22/08 no CLAUDE.md,
   e a razão de o tour existir.
2. O banco de teste nasce SEM `consignment_stock_account_id`. Sem conta, o
   método não escreve nada, a linha do defeito nunca roda, e nem um teste no
   perfil certo pegaria. Foi assim que o prod quebrou e o dev ficou verde: a
   produção tem a conta preenchida nas empresas que consignam.

Aqui os dois buracos se fecham no mesmo teste: perfil PELADO de consignação
(sem Inventário, sem Contatos) e a conta preenchida de propósito.
"""
from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "soc_fiscal")
class TestAclPrateleiraValorada(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def _conta_de_consignacao(self):
        """A conta 115xxx da empresa: é a presença dela que arma o defeito.

        Reaproveita se já existir -- num banco com plano de contas de verdade o
        código pode estar tomado, e o `code` é único por empresa.
        """
        Conta = self.env["account.account"]
        conta = Conta.search([("code", "=", "115997")], limit=1) or Conta.create({
            "code": "115997",
            "name": "Estoque em Consignação (ACL)",
            "account_type": "asset_current",
        })
        self.company.consignment_stock_account_id = conta
        return conta

    def _gerente_pelado(self):
        """O piso do que o Comercial tem: consignação e mais nada.

        Sem `stock.group_stock_manager` de propósito -- é a ausência dele que o
        teste mede. `base.group_user` entra porque sem empregado não há sessão;
        ele dá LEITURA de stock.location e nenhuma escrita.
        """
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "soc_gerente_valuation",
            "login": "soc_gerente_valuation",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [
                (4, self.env.ref("base.group_user").id),
                (4, self.env.ref("liber_soc_agreements.group_soc_manager").id),
            ],
        })

    def _contrato(self, usuario, nome):
        partner = self.env["res.partner"].create(
            {"name": nome, "is_company": True})
        return self.env["consignment.agreement"].with_user(usuario).create({
            "partner_id": partner.id,
            "company_id": self.company.id,
            "date_start": fields.Date.today(),
        })

    # ------------------------------------------------------------------

    def test_gerente_sem_inventario_ativa_com_a_conta_preenchida(self):
        """O clique que morreu em produção em 27/08, no perfil que o deu."""
        conta = self._conta_de_consignacao()
        gerente = self._gerente_pelado()
        self.assertFalse(
            gerente.has_group("stock.group_stock_manager"),
            "o teste perde o sentido se o perfil já for administrador de estoque")

        agr = self._contrato(gerente, "Livraria da Conta")
        agr.action_activate()
        # O flush é parte do teste: sem ele a escrita fica no cache e o
        # AccessError só apareceria no fim da requisição, longe daqui.
        self.env.flush_all()

        self.assertEqual(agr.state, "active")
        prateleira = agr.location_id
        self.assertTrue(
            prateleira,
            "ativar não criou a prateleira: é o Access Error de 26-27/08")
        self.assertEqual(
            prateleira.valuation_account_id, conta,
            "a prateleira nasceu sem a conta de estoque em consignação: o "
            "valor do livro consignado ficaria no Estoque do armazém")

    def test_sem_conta_na_empresa_a_prateleira_nasce_igual(self):
        """A contraprova: a casa que não parametrizou a conta não é punida.

        É este o caminho que o banco de teste percorria sozinho -- e é por ele
        percorrer só este que o defeito atravessou três dias.
        """
        self.company.consignment_stock_account_id = False
        gerente = self._gerente_pelado()

        agr = self._contrato(gerente, "Livraria Sem Conta")
        agr.action_activate()
        self.env.flush_all()

        self.assertEqual(agr.state, "active")
        self.assertTrue(agr.location_id)
        self.assertFalse(agr.location_id.valuation_account_id)
