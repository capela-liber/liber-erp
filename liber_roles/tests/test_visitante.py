# -*- coding: utf-8 -*-
"""O visitante enxerga tudo e não grava nada -- menos o chatter.

Este teste existe porque a promessa do visitante é uma promessa de segurança
feita a uma conta que vai circular em público. Promessa de segurança sem teste
é intenção.
"""

import os

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

        Esta lista é ÂNCORA, não régua: ela pina treze xmlids que não podem
        sumir. A régua de verdade é o
        `test_visitante_alcanca_toda_tela_do_produto`, que deriva a pergunta
        dos módulos instalados — porque esta lista, escrita à mão, ficou
        muito atrás do produto sem ninguém notar (ver o docstring de lá, e a
        medição de 11/09/2026).
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

    # ------------------------------------------- o guarda que não envelhece
    #: Telas que o visitante NÃO alcança, e o motivo. Cada entrada é uma
    #: decisão, não um bug tolerado — e sai daqui no dia em que a decisão
    #: mudar. Menu de Configuração não entra nesta lista porque o teste já o
    #: dispensa por construção: configurar é de administrador.
    EXCECOES = {
        'liber_support': (
            'Atendimento é conversa de cliente, não vitrine, e a conta '
            'pública circula. Decisão registrada no NOTES do módulo.'),
        'liber_transport': (
            'A tela mora dentro do Inventário, que a demo esconde de '
            'propósito — a demo mostra o Liber, não o Odoo cru.'),
        'liber_sales_dashboard': (
            'O menu é trancado por sales_team.group_sale_manager, que o '
            'visitante remove com (3, ...). Destrancar é decisão do módulo, '
            'não do visitante.'),
        'liber_roles': (
            'O painel de acesso exigiria base.group_system.'),
    }

    def _modulos_com_manual(self):
        """Os módulos cujo manual está PUBLICADO no site.

        É essa a régua da demo, e não "todo módulo liber_ instalado": o
        `liber_bookinfo`, por exemplo, é ensaio e não tem manual, então a demo
        não deve nada a ele. O catálogo de manuais é o diretório do
        `liber_site`, que é a fonte de verdade do que está publicado.

        Sem o `liber_site` na base (este módulo não depende dele), o teste não
        tem régua e se declara sem condição de medir.
        """
        from odoo.modules.module import get_module_path
        caminho = get_module_path('liber_site', display_warning=False)
        if not caminho:
            self.skipTest('liber_site ausente: sem catálogo de manuais')
        docs = os.path.join(caminho, 'static', 'docs')
        if not os.path.isdir(docs):
            self.skipTest('liber_site sem static/docs')
        publicados = {n[:-5] for n in os.listdir(docs) if n.endswith('.html')}
        instalados = self.env['ir.module.module'].search([
            ('name', 'like', 'liber_%'), ('state', '=', 'installed')])
        return [m for m in instalados.mapped('name') if m in publicados]

    def _menus_visiveis(self, user):
        dados = self.env['ir.ui.menu'].with_user(user).load_menus(False)
        return {int(k) for k in dados if str(k).isdigit()}

    def _e_configuracao(self, menu):
        """Configuração é de administrador, e não entra na régua da demo."""
        no = menu
        while no:
            if no.name in ('Configuration', 'Settings', 'Configuração',
                           'Definições', 'Preferences'):
                return True
            no = no.parent_id
        return False

    def test_visitante_alcanca_toda_tela_do_produto(self):
        """A régua da demo, derivada — não escrita à mão.

        O teste que existia aqui carregava um dicionário de treze menus,
        digitado quando o produto tinha vinte e sete manuais. O produto chegou
        a quarenta e seis módulos e ninguém atualizou a lista: em 11/09/2026 a
        medição mostrou o visitante alcançando 198 dos 475 menus, com DOZE
        apps de manual publicado sem abrir uma única tela — Olist, as três
        estantes de arquivos, Amazon, os dois relatórios de idade. A lista à
        mão não falhou por descuido; falhou porque lista à mão envelhece calada.

        Então a pergunta passa a ser feita ao banco: para todo menu que o
        ADMIN alcança e que pertence a um módulo `liber_*` instalado, o
        visitante também alcança — salvo Configuração (de administrador) e as
        EXCECOES acima, cada uma com motivo escrito.

        Assim um módulo novo entra no guarda no dia em que é instalado, sem
        ninguém se lembrar de nada.
        """
        admin = self.env.ref('base.user_admin')
        do_admin = self._menus_visiveis(admin)
        do_visitante = self._menus_visiveis(self.visitor)
        self.assertTrue(do_visitante, 'load_menus não devolveu menu nenhum')

        faltando = []
        for modulo in self._modulos_com_manual():
            if modulo in self.EXCECOES:
                continue
            ids = self.env['ir.model.data'].search([
                ('module', '=', modulo), ('model', '=', 'ir.ui.menu'),
            ]).mapped('res_id')
            for menu in self.env['ir.ui.menu'].browse(ids).exists():
                if menu.id not in do_admin or menu.id in do_visitante:
                    continue
                if self._e_configuracao(menu):
                    continue
                faltando.append('%s: %s' % (modulo, menu.complete_name))
        self.assertFalse(faltando, (
            'telas do produto que a demonstração não mostra (manual '
            'prometendo tela que não abre). Conceda o grupo de USUÁRIO do app '
            'ao visitante, ou registre a exceção em EXCECOES com o motivo: '
            '%s' % '; '.join(sorted(faltando))))

    def test_visitante_le_o_modelo_de_toda_tela_que_ve(self):
        """Ver o menu não basta: o clique tem de abrir.

        É a metade que o teste antigo não cobria, e é por onde os dois
        relatórios de idade escaparam: o menu deles não tinha grupo nenhum
        (todos veriam) mas a ACL do modelo liberava leitura só ao contador
        PLENO — e o visitante é contador somente-leitura. O Odoo então some
        com o menu, e o manual ficou falando de uma tela que a demo não tem.
        """
        do_visitante = self._menus_visiveis(self.visitor)
        sem_leitura = []
        for modulo in self._modulos_com_manual():
            ids = self.env['ir.model.data'].search([
                ('module', '=', modulo), ('model', '=', 'ir.ui.menu'),
            ]).mapped('res_id')
            for menu in self.env['ir.ui.menu'].browse(ids).exists():
                if menu.id not in do_visitante:
                    continue
                modelo = getattr(menu.action, 'res_model', None) if menu.action else None
                Model = self.env.get(modelo) if modelo else None
                if Model is None:
                    continue
                try:
                    Model.with_user(self.visitor).check_access('read')
                except AccessError:
                    sem_leitura.append('%s: %s (%s)' % (
                        modulo, menu.complete_name, modelo))
        self.assertFalse(sem_leitura, (
            'menu que a demo enxerga e cujo modelo ela não lê — o clique dá '
            'Access Error: %s' % '; '.join(sorted(sem_leitura))))

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
