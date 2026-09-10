# -*- coding: utf-8 -*-
"""A rede acima da filial: sugerida pela raiz do CNPJ, decidida pela ficha.

A raiz (8 primeiros dígitos) agrupa a Travessa inteira sozinha; a Leitura é
franquia -- uma raiz por loja -- e só se monta à mão. Por isso a regra é
sugestão-que-nunca-desfaz-escolha, e é isso que estes testes provam.
"""
from odoo.tests import TransactionCase, tagged

TRAVESSA_ROOT = "31004013"
TRAVESSA_BOTAFOGO = "31.004.013/0005-96"
TRAVESSA_VILLA = "31.004.013/0021-06"
VILA_CNPJ = "54.430.962/0005-33"
LEITURA_BANGU = "25.025.442/0001-13"


@tagged("post_install", "-at_install")
class TestPartnerGroup(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]
        cls.Group = cls.env["liber.partner.group"]
        # Num banco já semeado as redes de verdade existem -- e a mais antiga
        # vence a disputa pela raiz. O teste precisa de um tabuleiro limpo:
        # apaga as raízes pré-existentes (o rollback devolve tudo).
        cls.Group.search([]).write({"cnpj_roots": False})
        cls.travessa = cls.Group.create({
            "name": "Travessa (teste)", "cnpj_roots": "31.004.013"})
        cls.leitura = cls.Group.create({"name": "Leitura (teste)"})

    def test_raiz_do_cnpj_sugere_a_rede(self):
        loja = self.Partner.create({
            "name": "Travessa Botafogo", "vat": TRAVESSA_BOTAFOGO})
        self.assertEqual(loja.partner_group_id, self.travessa,
                         "a raiz declarada deve puxar a loja para a rede")

    def test_raiz_desconhecida_nao_sugere_nada(self):
        loja = self.Partner.create({
            "name": "Livraria da Vila Moema", "vat": VILA_CNPJ})
        self.assertFalse(loja.partner_group_id)

    def test_cpf_nunca_ganha_rede(self):
        pessoa = self.Partner.create({
            "name": "Leitor Comum", "vat": "123.456.789-09"})
        self.assertFalse(pessoa.partner_group_id)

    def test_escolha_manual_vence_a_sugestao(self):
        """A Leitura se monta à mão -- e a mão não pode ser desfeita."""
        loja = self.Partner.create({
            "name": "Leitura Bangu", "vat": LEITURA_BANGU,
            "partner_group_id": self.leitura.id})
        self.assertEqual(loja.partner_group_id, self.leitura)

        # Mesmo trocando o documento para uma raiz declarada de OUTRA rede,
        # a escolha feita fica.
        loja.vat = TRAVESSA_VILLA
        self.assertEqual(loja.partner_group_id, self.leitura,
                         "editar o vat não pode roubar a loja de sua rede")

    def test_raizes_quebradas_sao_ignoradas(self):
        torto = self.Group.create({
            "name": "Torto (teste)", "cnpj_roots": "abc, 123, 31.004"})
        self.assertEqual(torto._root_list(), [],
                         "pedaço sem 8 dígitos não é raiz")
        self.assertFalse(self.Group._group_for_vat("31004999000199"))

    def test_claim_puxa_orfaos_e_respeita_filiados(self):
        orfa = self.Partner.create({"name": "Travessa Ipanema"})
        orfa.vat = TRAVESSA_BOTAFOGO
        orfa.partner_group_id = False  # órfã de propósito
        filiada = self.Partner.create({
            "name": "Travessa fora da rede", "vat": TRAVESSA_VILLA,
            "partner_group_id": self.leitura.id})

        self.travessa.action_claim_matching_partners()

        self.assertEqual(orfa.partner_group_id, self.travessa)
        self.assertEqual(filiada.partner_group_id, self.leitura,
                         "quem já tem rede não é reagrupado")

    def test_contagem_de_membros(self):
        self.Partner.create({
            "name": "Travessa Leblon", "vat": "31.004.013/0009-10"})
        self.assertEqual(self.travessa.partner_count, 1)

    def test_eixo_sem_nenhum(self):
        """O eixo de leitura nunca é vazio: rede quando há, o cliente quando
        não -- foi o "Nenhum" com 18 mil unidades que pediu isso."""
        com_rede = self.Partner.create({
            "name": "Travessa Ipanema", "vat": TRAVESSA_BOTAFOGO})
        self.assertEqual(com_rede.commercial_group_display, "Travessa (teste)")

        sem_rede = self.Partner.create({
            "name": "Livraria Independente do Bixiga", "is_company": True})
        self.assertEqual(sem_rede.commercial_group_display,
                         "Livraria Independente do Bixiga",
                         "quem não é rede é ele mesmo, nunca 'Nenhum'")

    def test_contato_sobe_para_a_empresa(self):
        """Um comprador pendurado na loja conta na loja -- e na rede dela."""
        loja = self.Partner.create({
            "name": "Travessa Centro", "vat": TRAVESSA_VILLA})
        contato = self.Partner.create({
            "name": "Ana da Compras", "parent_id": loja.id,
            "is_company": False, "company_type": "person"})
        self.assertEqual(contato.commercial_group_display, "Travessa (teste)")

    def test_renomear_a_rede_arrasta_o_eixo(self):
        loja = self.Partner.create({
            "name": "Travessa Barra", "vat": TRAVESSA_BOTAFOGO})
        self.travessa.name = "Travessa Renomeada"
        self.assertEqual(loja.commercial_group_display, "Travessa Renomeada")

    # -- a busca -----------------------------------------------------------

    def test_agrupar_por_rede_vem_logo_depois_da_empresa(self):
        """A posição do filtro, afirmada como RELAÇÃO e não como número.

        Este módulo ancora o Grupo Comercial depois de Empresa
        (`group_company` position after), e ao fazê-lo empurrou o Canal de
        Vendas do `liber_partner_commercial` uma casa para a frente -- que
        tinha um teste cravado em "quarta posição" e ficou vermelho sem que
        nada estivesse errado na tela. O teste de lá virou relativo em
        03/09/2026, e este nasce assim de propósito: numa view que qualquer
        módulo herda, posição absoluta é afirmação que o próximo módulo
        derruba, e nunca por defeito.
        """
        from lxml import etree
        arch = etree.fromstring(self.env["res.partner"].get_view(
            view_id=self.env.ref("base.view_res_partner_filter").id,
            view_type="search")["arch"])
        nomes = arch.xpath('//group[@name="group_by"]/filter/@name')
        self.assertIn("group_partner_group", nomes)
        self.assertIn("group_company", nomes)
        self.assertEqual(
            nomes.index("group_partner_group"), nomes.index("group_company") + 1,
            f"Grupo Comercial saiu de junto de Empresa: {nomes}")
