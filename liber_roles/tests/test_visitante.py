# -*- coding: utf-8 -*-
"""O visitante enxerga tudo e não grava nada -- menos o chatter.

Este teste existe porque a promessa do visitante é uma promessa de segurança
feita a uma conta que vai circular em público. Promessa de segurança sem teste
é intenção.
"""

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_roles')
class TestVisitante(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        company = cls.env.ref('base.main_company')
        cls.visitor = Users.create({
            'name': 'Visitante', 'login': 'visitante@liber.test',
            'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
            'group_ids': [(4, cls.env.ref('liber_roles.group_visitante').id)],
        })
        cls.seller = Users.create({
            'name': 'Comercial', 'login': 'comercial@liber.test',
            'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
            'group_ids': [(4, cls.env.ref('liber_roles.group_comercial_gerente').id)],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Livraria de Teste'})
        cls.env.flush_all()
        cls.env.registry.clear_cache()

    @property
    def as_visitor(self):
        return self.env(user=self.visitor.id, su=False)

    # ------------------------------------------------------------ enxerga
    def test_visitante_le_o_sistema(self):
        """Nenhuma tela fica fechada: é uma demonstração, não uma vitrine."""
        env = self.as_visitor
        for model in ('res.partner', 'sale.order', 'account.move', 'product.template'):
            env[model].search([], limit=5).mapped('display_name')

    def test_visitante_abre_as_telas_que_tem_manual(self):
        """A régua da demo: se há manual publicado, a tela abre.

        Cada entrada aqui é um manual em liber_site/static/docs/. Falha aqui
        significa manual prometendo tela que a demonstração não mostra.

        A pergunta é feita por `load_menus`, não por `search`: `search` em
        ir.ui.menu NÃO filtra por grupo (devolve os ~94 menus para qualquer
        um), então um teste escrito sobre ele passa com qualquer configuração
        de acesso -- passa inclusive com a configuração errada. `load_menus`
        é o que o cliente web chama para montar o home, e é o único que
        responde a mesma coisa que o usuário vê.

        Ausentes de propósito: liber_roles (o painel de acesso exigiria
        base.group_system) e Dropbox/Drive/GitHub (módulos ainda não
        instalados nesta base -- quando entrarem, entram aqui também).
        """
        menus = {
            'Acordos de consignação': 'liber_soc_agreements.menu_consignment_root',
            'Remessas e retornos': 'liber_soc_moves.menu_consignment_moves',
            'Acerto de consignação': 'liber_soc_settlement.menu_consignment_settlements',
            'Auditoria pelo XML': 'liber_soc_audit.menu_consignment_audit',
            'Contratos de direitos': 'liber_copyright_contracts.menu_copyright_contracts_root',
            'Cálculo de royalties': 'liber_copyright_contracts_analytics.menu_edlab_reports',
            'IRRF sobre direitos': 'liber_copyright_contracts_taxes.menu_edlab_irrf_tables',
            'Pagamento de royalties': 'liber_copyright_contracts_payments.menu_edlab_bills',
            'Prestação de contas': 'liber_copyright_contracts_reports.menu_edlab_authors',
            'Importação de XML de NF-e': 'liber_nfe_xml.menu_nfe_xml_panel',
            'Notas de remessa': 'liber_nfe_remessa.menu_nfe_remessa',
            'Integração Metabooks': 'liber_metabooks_integration.menu_metabooks_root',
            'Orçamento': 'liber_budget.menu_budget_root',
        }
        dados = self.as_visitor['ir.ui.menu'].load_menus(False)
        # As chaves vêm misturadas: os ids dos menus (int e str) e 'root'.
        visiveis = {int(k) for k in dados if str(k).isdigit()}
        self.assertTrue(visiveis, "load_menus não devolveu menu nenhum")

        invisiveis = []
        for manual, xmlid in menus.items():
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu and menu.id not in visiveis:
                invisiveis.append('%s (%s)' % (manual, xmlid))
        self.assertFalse(
            invisiveis,
            "manuais publicados cuja tela o visitante não enxerga: %s"
            % ', '.join(invisiveis))

    def test_visitante_ve_a_vitrine_comercial(self):
        """Vendas e eCommerce não têm manual, mas são o que se vende.

        Um ERP de editora demonstrado sem o pedido e sem a loja não é
        demonstração. Os dois abrem com o mesmo grupo: sale.sale_menu_root é
        livre, mas os filhos que importam e o menu do eCommerce pedem
        group_sale_salesman.
        """
        dados = self.as_visitor['ir.ui.menu'].load_menus(False)
        visiveis = {int(k) for k in dados if str(k).isdigit()}
        for rotulo, xmlid in (('Vendas', 'sale.menu_sale_order'),
                              ('eCommerce', 'website_sale.menu_ecommerce')):
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                self.assertIn(menu.id, visiveis,
                              "%s faz parte da vitrine e sumiu do menu" % rotulo)

    def test_vitrine_de_vendas_nao_abre_vazia(self):
        """A armadilha do group_sale_salesman simples.

        Com ele, a regra de registro de sale.order filtra pelo vendedor dono.
        O visitante não é dono de pedido nenhum, então a tela abriria com
        zero linhas -- pior que fechada, porque parece defeito. É por isso
        que o grupo concedido é a variante _all_leads, e é isso que este
        teste trava: não basta o menu aparecer, os pedidos da casa têm de
        ser legíveis.
        """
        pedido = self.env['sale.order'].create({'partner_id': self.partner.id})
        self.env.flush_all()
        visto = self.as_visitor['sale.order'].search([('id', '=', pedido.id)])
        self.assertTrue(
            visto,
            "o visitante não enxerga pedidos de outros: a tela de Vendas "
            "abriria vazia (falta sales_team.group_sale_salesman_all_leads)")

    def test_nenhum_grupo_entra_de_carona(self):
        """As remoções são a última palavra, e isto é o que garante.

        implied_ids é uma sequência de comandos executada em ordem, e
        conceder um grupo dispara a cascata dos módulos que reagem a ele.
        Com os (3, ...) no topo da lista, conceder sale_salesman_all_leads
        no fim trouxe de volta project.group_project_user (via sale_project)
        e website.group_website_restricted_editor (via website_sale) — numa
        conta pública, sem erro nenhum aparecer.

        Este teste olha o grupo, não o menu: o app Site continua visível na
        demo de propósito, o que não pode voltar é o poder de EDITAR o site.
        Um teste só de menu não veria a diferença.
        """
        indesejados = (
            'project.group_project_user',
            'website.group_website_restricted_editor',
            'sales_team.group_sale_manager',
            'stock.group_stock_manager',
            'liber_soc_agreements.group_soc_manager',
            'liber_budget.group_budget_manager',
        )
        de_carona = [g for g in indesejados
                     if self.env.ref(g, raise_if_not_found=False)
                     and self.visitor.has_group(g)]
        self.assertFalse(
            de_carona,
            "grupos que a régua manda remover voltaram para o visitante "
            "(ordem dos comandos em implied_ids?): %s" % ', '.join(de_carona))

    def test_faxina_tira_a_carona_do_visitante(self):
        """O caso real: grupo concedido DIRETO, que nenhum (3, ...) alcança.

        Simula o que sale_project e website_sale fizeram em 27/07 ao ganharmos
        o grupo de vendas -- acrescentaram os grupos na conta, não nos
        implied_ids. É por isso que a limpeza tem de ser em Python e rodar em
        todo -u, e não uma linha a mais no XML.
        """
        caronas = self.env['res.groups']
        for xmlid in ('project.group_project_user',
                      'website.group_website_restricted_editor'):
            g = self.env.ref(xmlid, raise_if_not_found=False)
            if g:
                caronas |= g
        if not caronas:
            self.skipTest("nenhum dos grupos de carona existe nesta base")

        self.visitor.write({'group_ids': [(4, g.id) for g in caronas]})
        self.env.registry.clear_cache()
        self.assertTrue(
            all(self.visitor.has_group(g.get_external_id()[g.id]) for g in caronas),
            "o teste não conseguiu nem conceder a carona -- verifique o setup")

        self.env['res.users']._liber_faxina_do_visitante()

        ainda = [g.get_external_id()[g.id] for g in caronas
                 if self.visitor.has_group(g.get_external_id()[g.id])]
        self.assertFalse(
            ainda, "a faxina não removeu do visitante: %s" % ', '.join(ainda))

    def test_visitante_nao_ve_o_que_nao_tem_manual(self):
        """A régua corta dos dois lados, senão vira 'gerente em tudo' de novo.

        Compras, Inventário e Projeto não têm manual publicado e são apps do
        Odoo cru -- a demo mostra o Liber, não o Odoo. Este teste é o freio
        da v3: sem ele, a próxima frouxidão passa sem ninguém notar.
        """
        dados = self.as_visitor['ir.ui.menu'].load_menus(False)
        visiveis = {int(k) for k in dados if str(k).isdigit()}
        for rotulo, xmlid in (('Compras', 'purchase.menu_purchase_root'),
                              ('Inventário', 'stock.menu_stock_root'),
                              ('Projeto', 'project.menu_main_pm')):
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                self.assertNotIn(
                    menu.id, visiveis,
                    "%s não tem manual e não deveria aparecer na demo" % rotulo)

    # ------------------------------------------------------------ não grava
    def test_visitante_nao_emite_pedido(self):
        with self.assertRaises(AccessError):
            self.as_visitor['sale.order'].create({'partner_id': self.partner.id})

    def test_visitante_nao_altera_cadastro(self):
        with self.assertRaises(AccessError):
            self.as_visitor['res.partner'].browse(self.partner.id).write(
                {'comment': 'alterado pelo visitante'})

    def test_visitante_nao_mexe_na_contabilidade(self):
        with self.assertRaises(AccessError):
            self.as_visitor['account.move'].create(
                {'move_type': 'out_invoice', 'partner_id': self.partner.id})

    def test_visitante_nao_apaga(self):
        with self.assertRaises(AccessError):
            self.as_visitor['res.partner'].browse(self.partner.id).unlink()

    def test_recusa_explica_o_modo_visitante(self):
        """A mensagem é para quem está vendo o sistema pela primeira vez."""
        with self.assertRaises(AccessError) as e:
            self.as_visitor['sale.order'].create({'partner_id': self.partner.id})
        self.assertIn('Modo visitante', str(e.exception))

    # ------------------------------------------------------------ conversa
    def test_visitante_manda_mensagem(self):
        """Ler dá direito a comentar -- o regime que o portal já usa."""
        msg = self.as_visitor['res.partner'].browse(self.partner.id).message_post(
            body="Olá da apresentação!")
        self.assertTrue(msg)
        self.assertEqual(msg.author_id, self.visitor.partner_id)

    # -------------------------------------------------- ninguém mais regride
    def test_usuario_de_verdade_continua_gravando(self):
        """O guarda vale para o visitante, não para a casa."""
        env = self.env(user=self.seller.id, su=False)
        order = env['sale.order'].create({'partner_id': self.partner.id})
        self.assertTrue(order)
        env['res.partner'].browse(self.partner.id).write({'comment': 'legítimo'})
