# -*- coding: utf-8 -*-
"""O canal de vendas no cadastro do cliente.

O que importa testar aqui não é "o campo grava" -- é o que motivou o campo:
ele tem que ser POR EMPRESA (era assim no Odoo 15, em `ir.property`) e tem que
sobreviver ao fato de o Odoo 19 não ter mais `team_id` em `res.partner`.
"""
from lxml import etree

from odoo.tests.common import TransactionCase, tagged


# `post_install` pelo mesmo motivo da grade: o teste cria `crm.team`, e este
# módulo carrega antes do `crm` (depende só de `sales_team`). Num banco com o
# `crm` instalado, `crm_team.alias_id` já é NOT NULL enquanto o mixin do alias
# ainda não entrou no registro.
@tagged('post_install', '-at_install')
class TestPartnerSalesTeam(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # nada de dado de demonstração: ele muda entre versões.
        #
        # As EMPRESAS, porém, são as que o banco já tem. Criar uma com o
        # `account` instalado quebra no NOT NULL de `fiscalyear_last_day`: o
        # campo é delegado à empresa raiz (`_get_company_root_delegated_field_names`)
        # e por isso não entra no INSERT. Nada disso é deste módulo, e o que se
        # testa aqui é o campo do cliente, não a criação de empresa.
        cls.empresas = cls.env['res.company'].search([], order='id')
        cls.empresa_a = cls.empresas[0]
        cls.empresa_b = cls.empresas[1] if len(cls.empresas) > 1 else None
        cls.time_livrarias = cls.env['crm.team'].create({'name': 'Livrarias'})
        cls.time_redes = cls.env['crm.team'].create({'name': 'Redes'})
        cls.cliente = cls.env['res.partner'].create({'name': 'Livraria de Teste'})

    def test_campo_existe_no_parceiro(self):
        """O 19 tirou team_id de res.partner; este módulo devolve."""
        self.assertIn('team_id', self.env['res.partner']._fields)

    def test_grava_e_le(self):
        self.cliente.team_id = self.time_livrarias
        self.assertEqual(self.cliente.team_id, self.time_livrarias)

    def test_valor_e_por_empresa(self):
        """A razão de ser do company_dependent.

        No Odoo 15 o vínculo morava em `ir.property`, que é por empresa. Num
        grupo com mais de uma editora o mesmo cliente pode ser de um canal numa
        e de outro noutra -- guardar um valor só apagaria a distinção. São 233
        fichas assim no merge_02.
        """
        if not self.empresa_b:
            self.skipTest("precisa de duas empresas no banco")
        cliente_a = self.cliente.with_company(self.empresa_a)
        cliente_b = self.cliente.with_company(self.empresa_b)

        cliente_a.team_id = self.time_livrarias
        cliente_b.team_id = self.time_redes

        self.assertEqual(cliente_a.team_id, self.time_livrarias)
        self.assertEqual(cliente_b.team_id, self.time_redes,
                         "escrever numa empresa não pode vazar para a outra")

    def test_vazio_por_padrao(self):
        """Sem valor, o campo fica vazio -- não inventa o canal padrão.

        Vazio é informação: significa 'ninguém definiu ainda'. Se o campo
        caísse no `_get_default_team_id`, um cliente novo nasceria carimbado
        com a primeira equipe da empresa por sequência, que é ruído com cara
        de dado.
        """
        novo = self.env['res.partner'].create({'name': 'Cliente Sem Canal'})
        self.assertFalse(novo.team_id)

    def test_equipe_arquivada_continua_legivel(self):
        """Equipe arquivada não pode sumir do cadastro que aponta para ela.

        Na fusão das equipes de 2026 várias foram arquivadas; um cliente que
        apontasse para uma delas não pode passar a ler vazio, senão a correção
        de dados vira perda de dados.
        """
        self.cliente.team_id = self.time_redes
        self.time_redes.active = False
        self.cliente.invalidate_recordset(['team_id'])
        self.assertEqual(self.cliente.team_id.id, self.time_redes.id)

    def _lista_de_contatos(self):
        arch = self.env['res.partner'].get_view(
            view_id=self.env.ref('base.view_partner_tree').id, view_type='list')['arch']
        return etree.fromstring(arch)

    def test_coluna_na_lista_de_contatos(self):
        """O canal tem que estar na lista, não só na ficha.

        É na lista que se arruma cadastro em quantidade: foi assim que as
        filiais da Amazon, que a migração deixou espalhadas por três equipes,
        voltaram a um canal só.
        """
        arch = self._lista_de_contatos()
        self.assertIn('team_id', arch.xpath('//field/@name'))

    def test_lista_de_contatos_edita_em_bloco(self):
        """Vem do `base`, mas é do que depende a coluna servir para alguma coisa."""
        arch = self._lista_de_contatos()
        self.assertEqual(arch.get('multi_edit'), '1')

    def test_lista_le_a_equipe(self):
        """`team_id` é `company_dependent`: ler em lote não pode explodir.

        O campo mora num jsonb, não numa coluna própria; se o `search_read` da
        lista não o suportasse, a coluna quebraria a tela de contatos inteira.
        """
        self.cliente.team_id = self.time_livrarias
        lido = self.env['res.partner'].search_read(
            [('id', '=', self.cliente.id)], ['team_id'])
        self.assertEqual(lido[0]['team_id'][0], self.time_livrarias.id)

    def test_edicao_em_bloco_grava_a_equipe(self):
        """O caminho feliz do multi_edit na lista: um write para vários clientes."""
        outro = self.env['res.partner'].create({'name': 'Outra Livraria'})
        clientes = self.cliente | outro

        clientes.write({'team_id': self.time_redes.id})

        self.assertEqual(clientes.mapped('team_id'), self.time_redes)

    # -- a busca -----------------------------------------------------------
    #
    # Filtrar e agrupar por equipe é o que transforma a coluna em ferramenta.
    # E como `team_id` é `company_dependent` (jsonb, não coluna), não basta
    # conferir que o filtro está no XML: tem que agrupar e buscar de verdade.

    def _busca_de_contatos(self):
        arch = self.env['res.partner'].get_view(
            view_id=self.env.ref('base.view_res_partner_filter').id, view_type='search')['arch']
        return etree.fromstring(arch)

    def test_busca_tem_a_equipe(self):
        arch = self._busca_de_contatos()
        self.assertIn('team_id', arch.xpath('//search/field/@name'))

    def test_agrupar_por_equipe_e_o_quarto(self):
        """A posição é o pedido: depois de Vendedor, Empresa e País.

        No fim da lista o filtro existe e ninguém acha. Se o `base` reordenar
        os dele um dia, é aqui que se descobre.
        """
        nomes = self._busca_de_contatos().xpath('//group[@name="group_by"]/filter/@name')
        self.assertIn('group_by_team', nomes)
        self.assertEqual(nomes.index('group_by_team'), 3,
                         f"esperado em quarta posição, veio em {nomes.index('group_by_team') + 1}ª: {nomes}")

    def test_agrupar_por_equipe_funciona(self):
        """O caminho feliz, e a razão de o teste não parar no XML."""
        self.cliente.team_id = self.time_livrarias
        grupos = self.env['res.partner']._read_group(
            [('id', '=', self.cliente.id)], ['team_id'], ['__count'])
        self.assertEqual(grupos, [(self.time_livrarias, 1)])

    def test_buscar_pela_equipe(self):
        self.cliente.team_id = self.time_livrarias
        por_id = self.env['res.partner'].search([('team_id', '=', self.time_livrarias.id)])
        por_nome = self.env['res.partner'].search([('team_id', 'ilike', 'Livrarias')])
        self.assertIn(self.cliente, por_id)
        self.assertIn(self.cliente, por_nome, "buscar pelo nome da equipe também tem que achar")

    def test_busca_enxerga_so_a_empresa_ativa(self):
        """O caso de borda do company_dependent.

        Marcar a equipe numa empresa não pode fazer o cliente aparecer no
        filtro da outra -- senão o agrupar mente num grupo com mais de uma
        editora, que é exatamente o que o campo veio impedir.
        """
        if not self.empresa_b:
            self.skipTest("precisa de duas empresas no banco")
        self.cliente.with_company(self.empresa_a).team_id = self.time_livrarias

        na_a = self.env['res.partner'].with_company(self.empresa_a).search(
            [('team_id', '=', self.time_livrarias.id)])
        na_b = self.env['res.partner'].with_company(self.empresa_b).search(
            [('team_id', '=', self.time_livrarias.id)])

        self.assertIn(self.cliente, na_a)
        self.assertNotIn(self.cliente, na_b)

    def test_agrupar_por_equipe_inexistente_nao_explode(self):
        """Equipe apagada depois de marcada: o grupo some, a tela não quebra."""
        self.cliente.team_id = self.time_redes
        self.time_redes.unlink()

        grupos = self.env['res.partner']._read_group(
            [('id', '=', self.cliente.id)], ['team_id'], ['__count'])

        self.assertEqual(grupos, [(self.env['crm.team'], 1)])
