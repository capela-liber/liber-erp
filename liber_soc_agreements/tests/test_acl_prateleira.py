# -*- coding: utf-8 -*-
"""Quem fecha contrato de consignação não administra o estoque.

Nasceu de um bloqueio de produção (26/08/2026): a gerente comercial clicou
"Ativar" no AC/2026/0277 e levou

    Você não tem permissões para criar registros de 'Locais de inventário'
    (stock.location). Esta operação é permitida para os seguintes grupos:
    - Inventário/Administrador

A prateleira do cliente É um `stock.location`, e criar local no core do Odoo é
direito de `stock.group_stock_manager`. No prod, quatro contas tinham esse
direito -- nenhuma delas do Comercial. O teste antigo
(`test_activation_creates_shelf_and_flags_partner`) passava porque roda como
admin, que passa em tudo e não prova nada sobre o perfil.

Aqui a ativação roda no perfil da consignação PELADO -- sem Inventário, sem
Contatos --, que é o piso do que o Comercial tem. O tour de tela
correspondente mora no `liber_roles` (test_tour_comercial.py), onde os perfis
de verdade estão montados.

A segunda metade é a divisão de trabalho pedida em 26/08/2026: o contrato de
consignação é do GERENTE (o `liber_roles` já dizia "fecha contratos AC" na
descrição do perfil, mas o ACL nunca cobrou). O assistente opera o que existe
-- suspende, reativa --, e não abre contrato novo.
"""
from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "soc_agreements")
class TestAclPrateleira(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def _usuario(self, login, grupo):
        """Perfil de consignação PELADO: o grupo pedido e mais nada.

        Nada de `stock.group_stock_manager` aqui, de propósito -- é a ausência
        dele que o teste mede. `base.group_user` entra porque sem empregado não
        há sessão; ele dá LEITURA de stock.location e nenhuma escrita.
        """
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": login,
            "login": login,
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [
                (4, self.env.ref("base.group_user").id),
                (4, self.env.ref(grupo).id),
            ],
        })

    def _gerente(self):
        return self._usuario(
            "soc_gerente_acl", "liber_soc_agreements.group_soc_manager")

    def _assistente(self):
        return self._usuario(
            "soc_assistente_acl", "liber_soc_agreements.group_soc_user")

    def _livraria(self, nome):
        # O contato nasce como admin: cadastrar contato não é o que se mede
        # aqui, e o Assistente Comercial de verdade não cadastra.
        return self.env["res.partner"].create({"name": nome, "is_company": True})

    def _contrato(self, usuario, partner):
        return self.env["consignment.agreement"].with_user(usuario).create({
            "partner_id": partner.id,
            "company_id": self.company.id,
            "date_start": fields.Date.today(),
        })

    # ------------------------------------------------------------------
    # A prateleira
    # ------------------------------------------------------------------
    def test_gerente_sem_inventario_ativa_e_a_prateleira_nasce(self):
        """O clique que morreu em produção, no perfil que o deu."""
        gerente = self._gerente()
        self.assertFalse(
            gerente.has_group("stock.group_stock_manager"),
            "o teste perde o sentido se o perfil já for administrador de estoque")

        agr = self._contrato(gerente, self._livraria("Livraria da Prateleira"))
        agr.action_activate()

        self.assertEqual(agr.state, "active")
        prateleira = agr.location_id
        self.assertTrue(
            prateleira,
            "ativar o contrato não criou a prateleira: é o Access Error de 26/08")
        self.assertTrue(prateleira.is_consignment_shelf)
        self.assertEqual(prateleira.consignment_partner_id, agr.partner_id)
        # E os dois campos do passo seguinte, que precisam de escrita em
        # res.partner -- direito que o Comercial pode não ter.
        self.assertTrue(agr.partner_id.allow_consignment)
        self.assertEqual(agr.partner_id.consignment_location_id, prateleira)

    def test_a_raiz_co_tambem_nasce_sem_inventario(self):
        """A PRIMEIRA ativação da empresa cria a raiz CO, não só a prateleira.

        São duas criações de `stock.location`, e a raiz é a que passa
        despercebida: numa base que já tem a raiz, o defeito só aparece na
        prateleira. Numa empresa nova, morre uma linha antes.
        """
        # A empresa do banco de teste já costuma ter a sua raiz, e apagá-la
        # esbarra nas prateleiras penduradas. Em vez de apagar, TIRA-SE A
        # MARCA: `_soc_consignment_root` procura por ela, não acha, e cai no
        # ramo da criação -- que é o que se quer medir. Um `skipTest` aqui
        # deixaria o teste verde sem ter provado nada.
        antiga = self.env["stock.location"].search([
            ("is_consignment_root", "=", True),
            ("company_id", "=", self.company.id)])
        antiga.is_consignment_root = False
        gerente = self._gerente()

        agr = self._contrato(gerente, self._livraria("Livraria da Raiz"))
        agr.action_activate()

        raiz = agr.location_id.location_id
        self.assertTrue(raiz, "a prateleira nasceu solta, sem raiz")
        self.assertNotIn(raiz, antiga,
                         "o teste reaproveitou a raiz antiga e não provou nada")
        self.assertTrue(raiz.is_consignment_root)
        self.assertEqual(raiz.usage, "view")
        self.assertFalse(raiz.location_id,
                         "a raiz CO fica fora da árvore do armazém")

    # ------------------------------------------------------------------
    # Quem abre contrato, e quem só opera
    # ------------------------------------------------------------------
    def test_assistente_nao_abre_contrato(self):
        assistente = self._assistente()
        partner = self._livraria("Livraria Vedada")

        with self.assertRaises(
                AccessError,
                msg="o assistente abriu um contrato de consignação"):
            self._contrato(assistente, partner)

    def test_assistente_suspende_contrato_ativo(self):
        """Não criar não é não operar: a suspensão continua sendo dele."""
        gerente = self._gerente()
        agr = self._contrato(gerente, self._livraria("Livraria Suspensa"))
        agr.action_activate()

        # Sem isto a varredura mede o cache do usuário anterior.
        self.env.invalidate_all()
        assistente = self._assistente()
        agr.with_user(assistente).action_suspend()

        self.assertEqual(agr.state, "suspended")
        # e reativar também, que é a outra metade do mesmo botão
        agr.with_user(assistente).action_reactivate()
        self.assertEqual(agr.state, "active")

    def test_gerente_abre_contrato(self):
        """A contraprova: o direito não sumiu, mudou de dono."""
        gerente = self._gerente()
        agr = self._contrato(gerente, self._livraria("Livraria do Gerente"))
        self.assertEqual(agr.state, "draft")
