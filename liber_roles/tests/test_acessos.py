# -*- coding: utf-8 -*-
"""A revisão de acessos de 09/08/2026, travada teste a teste.

O levantamento que originou estas linhas está em `_mds/acessos-roles.md`: a
matriz foi lida do fecho transitivo real dos grupos no banco, e não do que o
XML dizia -- e a diferença entre os dois é que era o problema. Cinco coisas
saíram de lá para cá, e cada uma tem aqui o seu freio:

1. Marketing não era usuário interno (`website.group_website_restricted_editor`
   não implica `base.group_user` no v19). A função inteira era decorativa.
2. Ninguém na casa podia gravar a ficha de um livro.
3. O Financeiro/Gerente não via `Faturamento ‣ Contabilidade` -- no v19
   `group_account_manager` implica só `group_account_invoice`.
4. Ninguém exportava nada; agora exporta quem gerencia.
5. A Direção não podia cadastrar um contato.

O item que faltava -- o Comercial ainda com o app Inventário na base -- já
tinha teste (`test_logistica.py`) e ele estava VERMELHO. Não se acrescenta
teste para isso; conserta-se o XML e o teste que já existia fica verde.

Por que quase tudo aqui é `has_group` e não uma tela: estes são grupos sem
menu próprio (`allow_export`, `product_manager`, `account_user`). Onde existe
tela, a pergunta é feita por `load_menus`, nunca por `search` -- `search` em
ir.ui.menu não filtra por grupo, e um teste escrito sobre ele passa com
qualquer configuração de acesso, inclusive com a errada.
"""

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_roles')
class TestAcessos(TransactionCase):

    #: departamento -> os dois níveis. A régua da exportação e a do catálogo
    #: são varridas sobre esta grade, então acrescentar um departamento novo
    #: ao módulo e esquecê-lo aqui fica difícil.
    DEPARTAMENTOS = ('comercial', 'logistica', 'financeiro',
                     'editorial', 'juridico', 'marketing')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        company = cls.env.company

        def _usuario(funcao):
            # NB: sem `base.group_user` na mão de propósito. A tela de Usuários
            # do Odoo o concede por padrão, e foi exatamente esse padrão que
            # escondeu por semanas o fato de o Marketing não o ter. Um teste
            # que repetisse a gentileza da tela esconderia o mesmo buraco.
            return Users.create({
                'name': funcao, 'login': '%s@acessos.test' % funcao,
                'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
                'group_ids': [(4, cls.env.ref('liber_roles.group_%s' % funcao).id)],
            })

        cls.usuario = {'direcao': _usuario('direcao')}
        for dep in cls.DEPARTAMENTOS:
            for nivel in ('assistente', 'gerente'):
                chave = '%s_%s' % (dep, nivel)
                cls.usuario[chave] = _usuario(chave)
        cls.usuario['visitante'] = _usuario('visitante')

        #: alguém para chamar para conversar (ver a §7). É um usuário interno
        #: comum, sem função da casa: quem se convida no bate-papo é gente, não
        #: perfil.
        cls.colega = Users.create({
            'name': 'Colega', 'login': 'colega@acessos.test',
            'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
            'group_ids': [(4, cls.env.ref('base.group_user').id)],
        })

        cls.env.flush_all()
        cls.env.registry.clear_cache()

    # -- helpers -----------------------------------------------------------
    def _menus_visiveis(self, chave):
        usuario = self.usuario[chave]
        dados = self.env(user=usuario.id, su=False)['ir.ui.menu'].load_menus(False)
        return {int(k) for k in dados if str(k).isdigit()}

    def _assert_menu(self, chave, xmlid, rotulo, visivel):
        menu = self.env.ref(xmlid, raise_if_not_found=False)
        if not menu:
            self.skipTest('menu %s não existe nesta base' % xmlid)
        presente = menu.id in self._menus_visiveis(chave)
        if visivel:
            self.assertTrue(presente, '%s sumiu do menu de %s' % (rotulo, chave))
        else:
            self.assertFalse(
                presente, '%s aparece no menu de %s e não deveria'
                % (rotulo, chave))

    def _grava_ficha_do_livro(self, chave):
        """Cria e renomeia um product.template como o usuário."""
        env = self.env(user=self.usuario[chave].id, su=False)
        livro = env['product.template'].create({'name': 'Ficha de teste'})
        livro.write({'name': 'Ficha de teste (revisada)'})
        return livro

    # == 1. Marketing é gente de dentro ====================================
    def test_marketing_e_usuario_interno(self):
        """A falha mais silenciosa que este módulo já teve.

        `website.group_website_restricted_editor` é declarado no core sem
        `implied_ids` nenhum -- ao contrário de sale_salesman, stock_user,
        account_invoice e contract_user, que todos implicam `base.group_user`.
        O Marketing era o único departamento cuja ficha, sozinha, não fazia um
        usuário interno: nenhum menu do backend acendia.
        """
        for nivel in ('assistente', 'gerente'):
            chave = 'marketing_%s' % nivel
            self.assertTrue(
                self.usuario[chave].has_group('base.group_user'),
                'Marketing/%s não é usuário interno: a função não abre o '
                'Odoo, e só não doeu porque a tela de Usuários concede o '
                'grupo por fora' % nivel)
            self.assertFalse(
                self.usuario[chave].share,
                'Marketing/%s está marcado como usuário externo' % nivel)

    def test_marketing_abre_o_app_site(self):
        """O corolário, e a prova de que o conserto serviu para alguma coisa.

        O app Site é gated em `base.group_user`. Sem ele, o marketing não
        chegava nem à própria ferramenta -- editava o site sem poder abri-lo.
        """
        for nivel in ('assistente', 'gerente'):
            self._assert_menu('marketing_%s' % nivel,
                              'website.menu_website_configuration',
                              'Site', visivel=True)

    # == 1b. Toda função é usuário interno =================================
    def test_toda_funcao_e_usuario_interno(self):
        """A pergunta que a casa já errou duas vezes, agora varrida.

        `base.group_user` é o que faz alguém EXISTIR no Odoo: sem ele a
        função é decorativa e a pessoa esbarra em erro de acesso na primeira
        tela. O buraco já apareceu com o Marketing em 09/08/2026 (o
        `website.group_website_restricted_editor` não implica usuário interno
        no v19) e voltou em 11/08 com o Editorial, quando tirar o
        `stock.group_stock_user` cortou sem querer o único caminho que
        sobrava até ele.

        As duas vezes o grupo chegava DE CARONA, e foi por isso que sumiu sem
        aviso. Desde 11/08 cada Assistente o declara na própria lista, e este
        teste é o freio: varre as treze funções e não depende de carona
        nenhuma para passar.
        """
        for chave, usuario in self.usuario.items():
            self.assertTrue(
                usuario.has_group('base.group_user'),
                '%s não é usuário interno: a função inteira é decorativa, e '
                'a pessoa vai esbarrar em erro de acesso na primeira tela'
                % chave)

    # == 2. O catálogo tem dono ============================================
    def test_quem_faz_e_divulga_o_livro_grava_a_ficha(self):
        """Editorial e Marketing editam o catálogo.

        O Comercial SAIU desta lista em 11/08/2026 (ver `_mds/PERFIS.md`):
        "produto é livro, livro tem muitos metadados, está mais próximo do
        editorial e do marketing". Vender não exige criar produto — ler o
        catálogo para montar o pedido já é o padrão do usuário interno, e o
        outro lado disso está em test_o_catalogo_nao_e_de_todo_mundo.
        """
        for dep in ('editorial', 'marketing'):
            for nivel in ('assistente', 'gerente'):
                chave = '%s_%s' % (dep, nivel)
                livro = self._grava_ficha_do_livro(chave)
                self.assertTrue(
                    livro.id, '%s não conseguiu gravar a ficha do livro' % chave)

    def test_o_catalogo_nao_e_de_todo_mundo(self):
        """O outro lado da conta, que é o que faz a régua ser uma régua.

        Sem este teste, "o catálogo é do Editorial, do Comercial e do
        Marketing" vira "o catálogo é de quem pedir": basta alguém acrescentar
        o grupo por conveniência e ninguém percebe.
        """
        for dep in ('logistica', 'financeiro', 'juridico', 'comercial'):
            for nivel in ('assistente', 'gerente'):
                chave = '%s_%s' % (dep, nivel)
                with self.assertRaises(AccessError, msg=(
                        '%s grava na ficha do livro e não deveria' % chave)):
                    self._grava_ficha_do_livro(chave)

    def test_editorial_chega_ao_livro_sem_o_app_inventario(self):
        """O fim da contradição do NOTES §5, agora dos dois lados.

        O Editorial carregava `stock.group_stock_user` justamente para chegar
        ao livro pelo Inventário, e esbarrava no ACL de leitura do
        product.template: o app estava lá e a permissão que ele foi buscar,
        não. Em 09/08 ganhou a permissão; em 11/08 devolveu o app, que era a
        outra metade da correção ("editor edita texto" — `_mds/PERFIS.md`).

        As duas asserções juntas de propósito: separá-las deixaria passar o
        caso em que o app volta de carona com alguma concessão nova.
        """
        editorial = self.usuario['editorial_assistente']
        self.assertTrue(editorial.has_group('product.group_product_manager'))
        self.assertFalse(
            editorial.has_group('stock.group_stock_user'),
            'o Editorial voltou a carregar o app Inventário')

    # == 3. O Financeiro vê a contabilidade ================================
    def test_financeiro_gerente_ve_a_contabilidade(self):
        """"Contabilidade completa" era uma promessa não cumprida.

        No v19 `account.group_account_manager` implica UM grupo: o
        `group_account_invoice`. Não traz `readonly`, `basic` nem `user` -- a
        escada cheia mora no `account_accountant`, que é Enterprise. O gerente
        do Financeiro não via o menu Contabilidade nem o painel do próprio
        app; via a Direção, e via a conta pública de demonstração.
        """
        for xmlid, rotulo in (
                ('account.menu_finance', 'Faturamento'),
                ('account.menu_finance_entries', 'Faturamento ‣ Contabilidade'),
                ('account.menu_board_journal_1', 'Painel do Faturamento')):
            self._assert_menu('financeiro_gerente', xmlid, rotulo, visivel=True)

    def test_financeiro_assistente_continua_sendo_cobranca(self):
        """O recorte que NÃO mudou, e é preciso dizer que não mudou.

        Cobrança fatura, paga e concilia; não lê consolidado. Se o conserto do
        gerente tivesse escorregado para o assistente (bastava pendurar o
        grupo no lugar errado da implicação), o departamento inteiro viraria
        um nível só e ninguém veria.
        """
        assistente = self.usuario['financeiro_assistente']
        self.assertTrue(assistente.has_group('account.group_account_invoice'))
        self.assertFalse(
            assistente.has_group('account.group_account_user'),
            'a Cobrança ganhou os recursos contábeis completos: o Financeiro '
            'deixou de ter dois níveis')
        self._assert_menu('financeiro_assistente', 'account.menu_finance',
                          'Faturamento', visivel=True)
        self._assert_menu('financeiro_assistente', 'account.menu_finance_entries',
                          'Faturamento ‣ Contabilidade', visivel=False)

    # == 4. Exporta quem gerencia ==========================================
    def test_gerente_exporta_na_sua_area(self):
        """A régua nova, varrida sobre a grade inteira."""
        self.assertTrue(
            self.usuario['direcao'].has_group('base.group_allow_export'),
            'a Direção não exporta')
        for dep in self.DEPARTAMENTOS:
            self.assertTrue(
                self.usuario['%s_gerente' % dep].has_group(
                    'base.group_allow_export'),
                'o gerente do %s não exporta' % dep)

    def test_assistente_nao_exporta(self):
        """Exportar é tirar dado da casa, e isso é de quem responde por ela."""
        for dep in self.DEPARTAMENTOS:
            self.assertFalse(
                self.usuario['%s_assistente' % dep].has_group(
                    'base.group_allow_export'),
                'o assistente do %s exporta: a régua "exporta quem gerencia" '
                'deixou de significar alguma coisa' % dep)

    def test_visitante_nao_leva_a_base_embora(self):
        """A ausência mais deliberada do módulo, e a rodada de hoje mexeu
        justamente no grupo que a define -- então ela merece um freio.

        A conta é pública e circula. Sem escrita ela ainda poderia levar a
        base inteira num .xlsx, e agora ela lê Faturamento e Orçamento.
        """
        self.assertFalse(
            self.usuario['visitante'].has_group('base.group_allow_export'),
            'a conta pública de demonstração pode exportar a base')

    # == 5. Cadastrar contato é ato de gerência ============================
    def _cadastra_contato(self, chave):
        env = self.env(user=self.usuario[chave].id, su=False)
        return env['res.partner'].create(
            {'name': 'Livraria nova (%s)' % chave, 'is_company': True})

    def test_contato_e_de_quem_gerencia(self):
        """A régua de 09/08/2026, uniformizada em 20/08/2026.

        Comercial e Editorial cadastravam nos dois níveis; passaram a
        cadastrar só no Gerente. O Jurídico, que não cadastrava em nível
        nenhum, entrou no Gerente -- o contrato de direitos costuma ser o
        primeiro documento da casa a citar um autor, e mandar quem redige
        pedir o cadastro a outro departamento é inventar uma fila onde não
        havia trabalho.

        Em 20/08/2026 o cadastro deixou de ser concessão de departamento e
        virou marca de nível, como já era a exportação: entraram a Logística
        (o endereço de coleta e a transportadora nascem no depósito) e o
        Marketing (a lista de contatos é o mailing). A varredura passa a ser
        sobre a grade inteira -- departamento novo no módulo e esquecido aqui
        fica vermelho.
        """
        alvos = ['direcao'] + ['%s_gerente' % dep for dep in self.DEPARTAMENTOS]
        for chave in alvos:
            self.assertTrue(self._cadastra_contato(chave).id,
                            '%s não conseguiu cadastrar um contato' % chave)
            self.assertTrue(
                self.usuario[chave].has_group('base.group_partner_manager'),
                '%s cadastrou contato sem o partner_manager -- veio de carona '
                'de outro grupo, e a régua do nível não está escrita' % chave)

    def test_assistente_le_contato(self):
        """O outro degrau da régua: quem não cadastra, lê.

        Não há linha de XML nossa por trás disto, e é o ponto do teste: o ACL
        do core dá `res.partner` em leitura a `base.group_user` (`1,0,0,0`), e
        toda função da casa começa por `base.group_user`. Se um dia alguém
        estreitar esse ACL -- ou criar uma função sem o usuário interno, como
        já aconteceu com o Marketing em 09/08 --, é aqui que aparece.

        A leitura é cobrada com `read` de verdade, e não com `has_group`:
        grupo é meio, o que se prometeu foi enxergar o contato.
        """
        contato = self.env['res.partner'].create({'name': 'Livraria de leitura'})
        for dep in self.DEPARTAMENTOS:
            chave = '%s_assistente' % dep
            env = self.env(user=self.usuario[chave].id, su=False)
            self.assertEqual(
                env['res.partner'].browse(contato.id).name,
                'Livraria de leitura',
                '%s não lê contato -- o assistente ficou cego para o cadastro'
                % chave)

    def test_assistente_nao_cadastra_contato(self):
        """O outro lado da régua, sem o qual ela não é uma régua.

        Duas ausências nesta lista, e nenhuma é esquecimento: o COMERCIAL é o
        assunto do teste seguinte (o ACL que o concede é do `crm`, não nosso)
        e o FINANCEIRO é exceção pedida -- ver
        `test_cobranca_continua_cadastrando_o_cliente`.
        """
        for chave in ('logistica_assistente', 'editorial_assistente',
                      'juridico_assistente', 'marketing_assistente'):
            with self.assertRaises(AccessError, msg=(
                    '%s cadastrou contato: o cadastro não subiu para a '
                    'gerência' % chave)):
                self._cadastra_contato(chave)

    def test_o_comercial_e_a_fronteira_do_que_um_grupo_pode_prometer(self):
        """O assistente comercial CONTINUA cadastrando contato, e não há
        conserto -- só há dizer a verdade.

        A régua pedida foi "cadastrar contato é de gerência". Ela vale para o
        Editorial e para o Jurídico, e não vale para o Comercial, porque o ACL
        que concede o cadastro não é o nosso: o addon `crm` do core dá
        read/write/CREATE em res.partner a `sales_team.group_sale_salesman`
        (linha `res.partner.crm.user`). Quem vende cadastra cliente, por
        desenho do Odoo -- é o que faz funcionar criar o cliente na hora, de
        dentro da cotação.

        Tirar `group_sale_salesman` do Comercial para fechar essa porta seria
        tirar dele a venda. Não se faz.

        O que a saída de `base.group_partner_manager` mudou de verdade, e é o
        que este teste trava: o assistente perdeu o **unlink** -- não apaga
        mais contato. Criar sim, apagar não. É o recorte que existia para ser
        feito, e chamá-lo pelo nome certo vale mais do que fingir que a régua
        foi cumprida inteira.
        """
        contato = self._cadastra_contato('comercial_assistente')
        self.assertTrue(
            contato.id,
            'o assistente comercial deixou de cadastrar contato -- se isso '
            'passou a ser verdade, ele provavelmente perdeu a venda junto')
        self.assertFalse(
            self.usuario['comercial_assistente'].has_group(
                'base.group_partner_manager'))

        env = self.env(user=self.usuario['comercial_assistente'].id, su=False)
        with self.assertRaises(AccessError, msg=(
                'o assistente comercial apaga contato: a saída do '
                'partner_manager não surtiu efeito nenhum')):
            env['res.partner'].browse(contato.id).unlink()

    def test_cobranca_continua_cadastrando_o_cliente(self):
        """A exceção pedida, e o motivo dela.

        O Financeiro ficou intacto nos DOIS níveis: a Cobrança precisa abrir o
        cliente para poder faturá-lo, e submetê-la à fila de outro
        departamento pararia o faturamento. Se um dia alguém "uniformizar" a
        régua sem pensar, este teste é quem reclama.
        """
        for chave in ('financeiro_assistente', 'financeiro_gerente'):
            self.assertTrue(self._cadastra_contato(chave).id,
                            '%s não conseguiu cadastrar um contato' % chave)

    # == 6. A Direção é o superconjunto da casa ============================
    def test_direcao_e_a_soma_das_funcoes(self):
        """A definição, cobrada como definição e não como resultado.

        Desde 10/08/2026 a Direção não é uma lista de grupos que por acaso
        cobre as outras funções: ela É a soma delas, escrita assim no XML.
        Este teste guarda a FORMA -- os seis gerentes citados diretamente --,
        porque é a forma que faz a régua se manter sozinha. O teste seguinte
        guarda o efeito.

        Cobrar os dois não é redundância: o de efeito passaria também com a
        lista à mão de volta (verde no dia da mudança, vermelho meses depois,
        quando alguém desse algo a uma função e esquecesse a Direção). É
        exatamente esse esquecimento que a forma torna impossível.
        """
        direcao = self.env.ref('liber_roles.group_direcao')
        for dep in self.DEPARTAMENTOS:
            gerente = self.env.ref('liber_roles.group_%s_gerente' % dep)
            self.assertIn(
                gerente, direcao.implied_ids,
                'a Direção parou de citar o Gerente de %s: ou o departamento '
                'saiu da soma, ou alguém voltou a montar o perfil à mão' % dep)

    def test_direcao_alcanca_tudo_que_a_casa_alcanca(self):
        """O efeito da régua, medido contra a grade e não contra uma lista.

        Em vez de listar os grupos esperados -- lista que envelheceria no dia
        seguinte --, a pergunta é feita contra a própria grade: junte o fecho
        transitivo de TODAS as funções da casa e verifique que não sobra nada
        fora do fecho da Direção. Departamento novo, nível novo ou grupo novo
        em qualquer função entram nesta conta sem ninguém precisar lembrar.

        O VISITANTE FICA DE FORA DA CONTA, e essa é a mudança de 10/08/2026.
        Ele não é uma função da casa: é o único recorte restritivo do módulo,
        uma lista que SUBTRAI (`(3, ...)` mais a faxina em Python), e somar
        uma subtração a um superconjunto não quer dizer nada. O que ele havia
        pegado em 09/08 -- os grupos do Metabooks, que a conta pública via e a
        Direção não -- não se perde: chega pelo Marketing/Gerente, cujo
        `metabooks_manager_group` implica os outros dois. A §6b confere isso
        explicitamente, para que a lacuna de 09/08 continue tendo um freio com
        nome próprio depois que o visitante saiu daqui.
        """
        Groups = self.env['res.groups']
        funcoes = {chave: self.env.ref('liber_roles.group_%s' % chave)
                   for chave in self.usuario if chave != 'visitante'}
        # os próprios grupos-função não são acessos, são rótulos de perfil
        proprias = Groups.browse([g.id for g in funcoes.values()])
        direcao = funcoes['direcao'].all_implied_ids

        falta = Groups
        for chave, grupo in funcoes.items():
            if chave == 'direcao':
                continue
            falta |= grupo.all_implied_ids - direcao - proprias

        self.assertFalse(
            falta,
            'a Direção deixou de ser superconjunto da casa; falta(m): %s'
            % ', '.join(sorted(falta.mapped(
                lambda g: g.privilege_id.name and
                '%s/%s' % (g.privilege_id.name, g.name) or g.name))))

    # == 6b. o que o visitante deixou para trás ao sair da soma ============
    def test_direcao_ve_o_que_a_conta_publica_ve(self):
        """A lacuna de 09/08, com freio próprio agora que o visitante saiu.

        Quando o visitante entrava na conta do superconjunto, era ele quem
        cobrava estes grupos da Direção. Ele saiu (§6), e a cobrança não pode
        sair junto -- diretor que enxerga menos que a conta de demonstração
        pública é o descuido que aquela rodada encontrou.

        Não se compara com o fecho do visitante de propósito: ele é uma lista
        restritiva e vai continuar mudando por outros motivos. O que se cobra
        é o motivo concreto, nomeado.
        """
        direcao = self.env.ref('liber_roles.group_direcao').all_implied_ids
        for xmlid in ('liber_metabooks_integration.metabooks_product_group',
                      'liber_metabooks_integration.metadata_group'):
            grupo = self.env.ref(xmlid, raise_if_not_found=False)
            if not grupo:
                continue
            self.assertIn(
                grupo, direcao,
                'a Direção perdeu %s -- a conta pública de demonstração vê '
                'os botões da MVB e o diretor não' % xmlid)

    def test_direcao_configura_o_deposito_e_a_contabilidade(self):
        """As duas linhas mais afiadas da virada, nomeadas.

        `stock.group_stock_manager` traz o ajuste de inventário (reescreve
        saldo físico) e `account.group_account_manager` traz plano de contas e
        impostos -- configuração com efeito fiscal. As duas foram oferecidas
        como exceção possível e a direção escolheu incluir. Se um dia a
        escolha se inverter, é aqui que a inversão aparece.
        """
        direcao = self.usuario['direcao']
        self.assertTrue(direcao.has_group('stock.group_stock_manager'))
        self.assertTrue(direcao.has_group('account.group_account_manager'))

    # == 7. O bate-papo é de todo mundo ====================================
    #
    # Pedido da direção em 10/08/2026: "todos os usuários precisariam ter
    # acesso ao bate-papo; as pessoas podem adicionar e chamar gente para
    # conversar". Na hora do pedido isso JÁ era verdade -- e é justamente por
    # isso que estes testes existem. Um acesso que ninguém trava é um acesso
    # que qualquer linha futura pode tirar em silêncio: basta um perfil novo
    # nascer sem `base.group_user` (foi o que aconteceu com o Marketing até
    # 09/08/2026, e com ele o Odoo inteiro não abria), ou alguém pendurar um
    # grupo em `discuss.channel.group_public_id` achando que organiza.
    #
    # O visitante entra na conta de propósito. Ele é a ÚNICA exceção ao "não
    # grava nada": a allowlist de models/ir_model_access.py libera
    # discuss.channel e discuss.channel.member desde o primeiro dia, porque
    # numa demonstração pública conversar é a coisa mais inofensiva e mais
    # convincente que a conta pode fazer.

    def _todos_os_perfis(self):
        return sorted(self.usuario)

    def test_todo_perfil_abre_o_bate_papo(self):
        """O menu do Discuss é gated em `base.group_user`, e só nele.

        Este teste é o irmão de test_marketing_e_usuario_interno: se um
        departamento voltar a nascer sem o grupo de usuário interno, é aqui
        que aparece com o nome do bate-papo, que é o sintoma que as pessoas
        relatam.
        """
        for chave in self._todos_os_perfis():
            self._assert_menu(chave, 'mail.menu_root_discuss',
                              'Bate-papo (Discuss)', visivel=True)

    def test_todo_perfil_cria_canal_e_chama_gente(self):
        """Criar canal, abrir conversa em grupo e ACRESCENTAR alguém.

        Os três verbos do pedido, exercitados pela mesma API que a tela usa
        (`_create_channel`, `_create_group`, `add_members`) -- e não por um
        `create()` cru, que passaria por cima das regras de registro do
        `discuss.channel.member` e não provaria nada sobre convidar gente.
        """
        alvo = self.colega.partner_id
        for chave in self._todos_os_perfis():
            env = self.env(user=self.usuario[chave].id, su=False)

            canal = env['discuss.channel']._create_channel(
                name='canal-%s' % chave,
                group_id=self.env.ref('base.group_user').id)
            self.assertTrue(canal.id, '%s não conseguiu criar um canal' % chave)

            canal.add_members(partner_ids=[alvo.id])
            self.assertIn(
                alvo, canal.channel_member_ids.partner_id,
                '%s criou o canal mas não conseguiu chamar ninguém para ele'
                % chave)

            grupo = env['discuss.channel']._create_group(
                partners_to=[alvo.id], name='conversa-%s' % chave)
            self.assertTrue(
                grupo.id,
                '%s não conseguiu abrir uma conversa com um colega' % chave)

    def test_visitante_conversa_mas_segue_sem_gravar_o_resto(self):
        """A exceção do visitante é estreita, e a estreiteza é o ponto.

        Se um dia alguém "simplificar" a allowlist do ir_model_access.py, as
        duas metades desta asserção caem juntas e em direções opostas: ou o
        visitante para de conversar (e a demonstração fica muda), ou ele passa
        a gravar documento (e a conta pública deixa de ser pública).
        """
        env = self.env(user=self.usuario['visitante'].id, su=False)
        canal = env['discuss.channel']._create_channel(
            name='canal-do-visitante',
            group_id=self.env.ref('base.group_user').id)
        self.assertTrue(canal.id)

        with self.assertRaises(AccessError, msg=(
                'o visitante gravou um contato: a allowlist do bate-papo '
                'vazou para o resto do sistema')):
            env['res.partner'].create({'name': 'Contato proibido'})

    # == 8. O catálogo de aplicativos é do administrador ====================
    def test_ninguem_da_casa_ve_o_menu_aplicativos(self):
        """Relato da direção em 10/08/2026, e a causa não era a nossa grade.

        Todo mundo via "Aplicativos" -- do assistente de logística ao
        visitante da demonstração pública -- porque o módulo
        `base_install_request` do core (auto_install, depende só de `mail`)
        faz `group_ids = (5, 0, 0)` no menu, esvaziando a trava que o `base`
        tinha escrito. A intenção dele é deixar o usuário comum PEDIR a
        instalação de um app; a nossa é que o catálogo de módulos seja de
        quem administra o sistema.

        security/menu_aplicativos.xml devolve `base.group_system`, e o
        manifest passou a depender de `base_install_request` só para garantir
        a ordem de carga. Se alguém tirar essa dependência, o menu volta para
        a casa inteira sem erro nenhum -- e é este teste que grita.
        """
        for chave in self._todos_os_perfis():
            self._assert_menu(chave, 'base.menu_management',
                              'Aplicativos', visivel=False)

    def test_o_administrador_continua_vendo_os_aplicativos(self):
        """O outro lado: devolver a trava não pode ter fechado a porta de quem
        instala módulo. Sem esta metade, o teste acima passaria com o menu
        apagado para todos -- inclusive para quem precisa dele.
        """
        admin = self.env.ref('base.user_admin', raise_if_not_found=False)
        if not admin or not admin.has_group('base.group_system'):
            self.skipTest('esta base não tem o admin padrão')
        menu = self.env.ref('base.menu_management')
        dados = self.env(user=admin.id, su=False)['ir.ui.menu'].load_menus(False)
        self.assertIn(
            menu.id, {int(k) for k in dados if str(k).isdigit()},
            'o administrador perdeu o menu Aplicativos')

    # == 9. Projetos: o gerente opera, o assistente lê ======================
    #
    # Pedido da direção em 10/08/2026. A metade do gerente é um grupo do Odoo;
    # a do assistente foi a interessante: o Odoo JÁ dava a leitura (o ACL de
    # project.project para base.group_user é 1,0,0,0 e a regra de tarefa para
    # empregado é r1 w0 c0 u0) e só o menu estava fechado. Por isso o
    # group_project_task_editor não concede nada -- é uma chave de porta.

    def test_editorial_redige_contrato_mas_nao_assina(self):
        """10/08/2026: o Editorial perdeu a gerência de contratos.

        A régua da casa é "quem redige não assina". O Jurídico já vivia assim
        desde 05/08; o Editorial era a porta que ainda a contornava, porque o
        Gerente dele carregava `contract_manager` e portanto confirmava,
        cancelava e renovava contrato sem passar por ninguém.

        As duas asserções são uma frase só. A primeira sozinha passaria mesmo
        que ele tivesse perdido o app inteiro -- e perder o app não era o
        pedido: ele continua consultando e redigindo. A segunda sozinha não
        provaria que a remoção `(3, ...)` chegou ao banco, porque um perfil sem
        contrato nenhum também a satisfaz.
        """
        gerente = self.usuario['editorial_gerente']
        self.assertTrue(
            gerente.has_group('liber_copyright_contracts.group_contract_user'),
            'o Editorial/Gerente perdeu o contrato inteiro -- o pedido era '
            'tirar a assinatura, não a leitura nem a redação')
        self.assertFalse(
            gerente.has_group(
                'liber_copyright_contracts.group_contract_manager'),
            'o Editorial/Gerente ainda assina contrato: a remoção não chegou '
            'ao banco (lembre que (4, ...) não desfaz aresta -- é (3, ...), e '
            'por último na lista)')

    def test_direcao_nao_perdeu_o_contrato_junto(self):
        """A remoção do Editorial não pode respingar na Direção.

        A Direção é a soma dos seis Gerentes, e um `(3, ...)` num deles é
        exatamente o tipo de mudança que a esvazia sem ninguém perceber. Ela
        segue assinando porque alcança `contract_manager` pelo Jurídico.
        """
        self.assertTrue(
            self.usuario['direcao'].has_group(
                'liber_copyright_contracts.group_contract_manager'),
            'a Direção deixou de assinar contrato: a saída do Editorial '
            'respingou na soma')

    def test_editorial_gerente_opera_projetos(self):
        """Acesso pleno: cria projeto, que é o que o nível de usuário não faz.

        O `group_project_user` NÃO escreve project.project (ACL 1,0,0,0), então
        criar é a prova certa de que o nível é o de gerente.
        """
        env = self.env(user=self.usuario['editorial_gerente'].id, su=False)
        projeto = env['project.project'].create({'name': 'Coleção nova'})
        self.assertTrue(projeto.id,
                        'o Editorial/Gerente não conseguiu criar um projeto')

    def test_editorial_assistente_trabalha_a_tarefa(self):
        """A régua apertada da tarde de 10/08: escreve tarefa, não cria tarefa.

        As três asserções são uma frase só, e separá-las esconderia o caso em
        que a escrita chega junto com a criação — que é o que teria acontecido
        se o grupo escolhido fosse o `project.group_project_user` do Odoo.
        """
        projeto = self.env['project.project'].create(
            {'name': 'Coleção em andamento',
             'privacy_visibility': 'employees'})
        tarefa = self.env['project.task'].create(
            {'name': 'Revisar provas', 'project_id': projeto.id})
        env = self.env(user=self.usuario['editorial_assistente'].id, su=False)

        env['project.task'].browse(tarefa.id).write({'name': 'Revisar provas 2'})
        self.assertEqual(tarefa.name, 'Revisar provas 2',
                         'o assistente do Editorial não conseguiu escrever '
                         'na tarefa do projeto')

        with self.assertRaises(AccessError, msg=(
                'o assistente criou tarefa dentro de um projeto: era para '
                'poder escrever, não criar')):
            env['project.task'].create(
                {'name': 'Tarefa proibida', 'project_id': projeto.id})

    def test_a_tarefa_pessoal_continua_sendo_de_todos(self):
        """A fronteira que o pedido não alcança, e é bom que não alcance.

        "Não pode criar tarefas" vale para tarefa DE PROJETO. A tarefa
        privada — sem projeto, só dele — é a "Minhas tarefas" nativa do Odoo,
        um bloco de notas particular que todo empregado tem. Barrá-la exigiria
        mexer no ACL de `base.group_user`, ou seja, tirá-la da casa inteira.
        """
        env = self.env(user=self.usuario['editorial_assistente'].id, su=False)
        pessoal = env['project.task'].create({'name': 'Lembrete meu'})
        self.assertTrue(pessoal.id,
                        'o assistente perdeu a própria lista de tarefas')
        self.assertFalse(pessoal.project_id)

    def test_editorial_assistente_le_projeto_e_nao_grava(self):
        """Leitura, e só. As duas metades no mesmo teste de propósito: separá-las
        deixaria passar o caso em que a leitura some junto com a escrita.
        """
        projeto = self.env['project.project'].create(
            {'name': 'Projeto que o assistente lê'})
        env = self.env(user=self.usuario['editorial_assistente'].id, su=False)

        self.assertEqual(
            env['project.project'].browse(projeto.id).name,
            'Projeto que o assistente lê',
            'o Editorial/Assistente não consegue ler o projeto')

        with self.assertRaises(AccessError, msg=(
                'o Editorial/Assistente gravou no projeto: era para ser '
                'leitura')):
            env['project.project'].browse(projeto.id).write({'name': 'Mexido'})
        with self.assertRaises(AccessError, msg=(
                'o Editorial/Assistente criou projeto: era para ser leitura')):
            env['project.project'].create({'name': 'Projeto proibido'})

    def test_marketing_gerente_trabalha_a_tarefa_como_o_editorial(self):
        """"Marketing/Gerente tem acesso idêntico ao Editorial/Assistente."

        Idêntico é uma palavra forte, e é a asserção: em vez de repetir a
        lista de grupos de projeto dos dois — que envelheceria no dia em que
        um deles mudasse —, compara-se o recorte de PROJETO de um com o do
        outro. Se alguém mexer num e esquecer o outro, é aqui que aparece.
        """
        de_projeto = (
            self.env.ref('liber_roles.group_project_reader')
            | self.env.ref('liber_roles.group_project_task_editor')
            | self.env.ref('project.group_project_user')
            | self.env.ref('project.group_project_manager'))
        editorial = self._perfil_projeto('editorial_assistente', de_projeto)
        marketing = self._perfil_projeto('marketing_gerente', de_projeto)
        self.assertEqual(
            editorial, marketing,
            'Marketing/Gerente e Editorial/Assistente deixaram de ter o mesmo '
            'acesso a Projetos')

    def test_marketing_assistente_le_e_comenta_e_nao_grava(self):
        """"Pode só ler e deixar comentários laterais."

        O comentário é a parte que não sai de graça: para o Odoo, postar no
        chatter é ato de ESCRITA no documento (`_mail_post_access`). Quem só
        lê teria o chatter aberto e mudo — pior que fechado. O
        models/mail_thread.py baixa a exigência para `read` nestes dois
        modelos, e este teste é quem garante que a exceção existe e que ela
        não virou uma licença para gravar.
        """
        projeto = self.env['project.project'].create(
            {'name': 'Campanha de lançamento',
             'privacy_visibility': 'employees'})
        tarefa = self.env['project.task'].create(
            {'name': 'Peça para a livraria', 'project_id': projeto.id})
        env = self.env(user=self.usuario['marketing_assistente'].id, su=False)

        self.assertEqual(env['project.task'].browse(tarefa.id).name,
                         'Peça para a livraria',
                         'o Marketing/Assistente não lê a tarefa')

        recado = env['project.task'].browse(tarefa.id).message_post(
            body='Dá para adiantar esta?', message_type='comment')
        self.assertTrue(recado.id,
                        'o Marketing/Assistente não conseguiu comentar')

        with self.assertRaises(AccessError, msg=(
                'o Marketing/Assistente gravou na tarefa: era para ler e '
                'comentar')):
            env['project.task'].browse(tarefa.id).write({'name': 'Mexido'})
        with self.assertRaises(AccessError, msg=(
                'o Marketing/Assistente gravou no projeto')):
            env['project.project'].browse(projeto.id).write({'name': 'Mexido'})

    def _perfil_projeto(self, chave, universo):
        """Os grupos de projeto que este perfil alcança, e só eles."""
        return self.env.ref('liber_roles.group_%s' % chave).all_implied_ids & universo

    def test_o_assistente_abre_o_app_projetos(self):
        """A chave de menu, que é a única coisa que o grupo novo faz.

        Sem ela a leitura existe e não serve para nada: o menu raiz do
        `project` é gated nos dois grupos nativos, e nenhum deles cabe aqui.
        """
        self._assert_menu('editorial_assistente', 'project.menu_main_pm',
                          'Projetos', visivel=True)
        self._assert_menu('editorial_gerente', 'project.menu_main_pm',
                          'Projetos', visivel=True)

    def test_o_juridico_tambem_abre_o_app_projetos(self):
        """"Acessa os próprios projetos" — decidido em 11/08/2026.

        Entrou no degrau da casa (escrever na tarefa que enxerga) e não no
        `project.group_project_user` do Odoo, que cria e apaga tarefa em
        projeto alheio. Ver o comentário dos dois grupos no XML.
        """
        for chave in ('juridico_assistente', 'juridico_gerente'):
            self._assert_menu(chave, 'project.menu_main_pm',
                              'Projetos', visivel=True)

    def test_projetos_nao_vazou_para_quem_nao_pediu(self):
        """O outro lado: a chave abre para quem tem projeto, não para a casa.

        Se alguém trocar o `(4, ...)` do menu por `base.group_user` "para
        simplificar", o app Projetos aparece para todo mundo -- e é este teste
        que reclama. O Jurídico saiu da lista em 11/08 por decisão, não por
        vazamento: ver o teste logo acima.
        """
        for chave in ('comercial_assistente', 'logistica_assistente',
                      'financeiro_assistente', 'visitante'):
            self._assert_menu(chave, 'project.menu_main_pm',
                              'Projetos', visivel=False)

    # == 10. Metabooks: a ficha do livro e a maquinaria são coisas diferentes
    #
    # Pedido da direção em 10/08/2026, sobre as telas do app: o Marketing/
    # Gerente com acesso pleno (cria produto, sincroniza, importa catálogo); o
    # Marketing/Assistente editando produto e sincronizando UM livro, sem mexer
    # na maquinaria de catálogo; o Editorial/Gerente criando produto e
    # consultando "Livros".
    #
    # O que o levantamento achou pelo caminho, e que ninguém tinha pedido: as
    # dezessete linhas do ir.model.access do módulo estavam com a coluna de
    # grupo VAZIA. Coluna vazia não é "sem opinião" — é acesso a todo usuário
    # interno. Qualquer pessoa da casa podia disparar uma importação do
    # catálogo inteiro da MVB ou reescrever a tabela BISAC.

    #: menus da maquinaria: importar, enviar, editar tabela de referência
    MENUS_MAQUINARIA = (
        ('liber_metabooks_integration.menu_metabooks_imports', 'Importações'),
        ('liber_metabooks_integration.menu_metabooks_exports', 'Envios'),
        ('liber_metabooks_integration.menu_metabooks_catalogue', 'Catálogo'),
    )

    def _job_de_importacao(self, chave):
        env = self.env(user=self.usuario[chave].id, su=False)
        return env['metabooks.import.job'].create(
            {'mvb_id': 'BR0090213', 'job_type': 'catalog'})

    def test_marketing_gerente_tem_o_metabooks_inteiro(self):
        """Pleno: importa catálogo, envia lote, edita referência."""
        self.assertTrue(self.usuario['marketing_gerente'].has_group(
            'liber_metabooks_integration.metabooks_manager_group'))
        for xmlid, rotulo in self.MENUS_MAQUINARIA:
            self._assert_menu('marketing_gerente', xmlid, rotulo, visivel=True)
        self.assertTrue(self._job_de_importacao('marketing_gerente').id,
                        'o Marketing/Gerente não conseguiu criar uma '
                        'importação de catálogo')

    def test_marketing_assistente_sincroniza_o_livro_e_nao_a_maquina(self):
        """A linha mais fina do pedido, e as duas metades juntas.

        Ele edita a ficha e sincroniza UM título (os dois botões do formulário
        do produto vêm do metabooks_product_group); não dispara importação de
        catálogo nem mexe nas tabelas de referência.
        """
        assistente = self.usuario['marketing_assistente']
        self.assertTrue(assistente.has_group(
            'liber_metabooks_integration.metabooks_product_group'),
            'o Marketing/Assistente perdeu a sincronização por livro')
        self.assertFalse(assistente.has_group(
            'liber_metabooks_integration.metabooks_manager_group'),
            'o Marketing/Assistente ganhou a maquinaria de catálogo')

        self._assert_menu('marketing_assistente',
                          'liber_metabooks_integration.menu_metabooks_books',
                          'Livros', visivel=True)
        for xmlid, rotulo in self.MENUS_MAQUINARIA:
            self._assert_menu('marketing_assistente', xmlid, rotulo,
                              visivel=False)

        with self.assertRaises(AccessError, msg=(
                'o Marketing/Assistente disparou uma importação de catálogo')):
            self._job_de_importacao('marketing_assistente')

    def test_editorial_gerente_cria_produto_e_consulta_livros(self):
        """O pedido do Editorial: criar produto e olhar a estante."""
        self._assert_menu('editorial_gerente',
                          'liber_metabooks_integration.menu_metabooks_books',
                          'Livros', visivel=True)
        livro = self._grava_ficha_do_livro('editorial_gerente')
        self.assertTrue(livro.id)
        for xmlid, rotulo in self.MENUS_MAQUINARIA:
            self._assert_menu('editorial_gerente', xmlid, rotulo,
                              visivel=False)

    def test_a_maquinaria_do_metabooks_nao_e_de_todo_mundo(self):
        """O corte que não existia: coluna de grupo vazia no ir.model.access.

        Sem este teste, a volta ao estado anterior é uma linha de CSV — e uma
        linha de CSV não faz barulho nenhum.
        """
        for chave in ('comercial_assistente', 'logistica_assistente',
                      'financeiro_assistente', 'juridico_assistente',
                      'editorial_assistente'):
            with self.assertRaises(AccessError, msg=(
                    '%s dispara importação de catálogo da MVB' % chave)):
                self._job_de_importacao(chave)

    # == 11. As concessões de 11/08/2026 ===================================
    #
    # Cada uma destas veio de uma frase do `_mds/PERFIS.md`, e o teste repete a
    # frase de propósito: o dia em que alguém apagar a linha do XML, o vermelho
    # aqui diz qual decisão está sendo desfeita, não só qual grupo sumiu.

    def test_o_comercial_fatura_a_nota_de_venda(self):
        """"Acessa principalmente Sales e tem necessidade de faturar notas."

        Antes de 11/08 o Comercial não tinha nada de faturamento: vendia e
        parava na cotação.
        """
        for nivel in ('assistente', 'gerente'):
            self.assertTrue(
                self.usuario['comercial_%s' % nivel].has_group(
                    'account.group_account_invoice'),
                'o Comercial/%s não fatura a própria venda' % nivel)

    def test_o_gerente_comercial_cancela_o_que_tem_movimento(self):
        """"Precisa cancelar um documento que já tenha um movimento."

        Não existe grupo mais estreito no Odoo: cancelar transferência não
        confirmada pede `stock.group_stock_user`. O assistente segue de fora —
        é o outro lado da régua, e sem ele isto vira "o Comercial voltou a ter
        o app Inventário".
        """
        self.assertTrue(
            self.usuario['comercial_gerente'].has_group('stock.group_stock_user'))
        self.assertFalse(
            self.usuario['comercial_assistente'].has_group('stock.group_stock_user'),
            'o Inventário desceu para o assistente comercial')

    def test_o_financeiro_gerente_e_um_controller(self):
        """"Ele é mais que gerente, é um controller": painel, orçamento e o
        visto na conta bancária do fornecedor.

        O `group_validate_bank_account` não é extrato nem conciliação (esses
        vêm do account_manager, que ele já tem): é o controle antifraude que
        libera conta bancária de fornecedor cadastrada ou alterada.
        """
        gerente = self.usuario['financeiro_gerente']
        for grupo, o_que in (
                ('spreadsheet_dashboard.group_dashboard_manager', 'monta painel'),
                ('liber_budget.group_budget_manager', 'administra o orçamento'),
                ('account.group_validate_bank_account', 'aprova conta bancária'),
                ('purchase.group_purchase_manager', 'administra as compras')):
            self.assertTrue(gerente.has_group(grupo),
                            'o Financeiro/Gerente não %s' % o_que)

    def test_o_assistente_financeiro_leva_a_po_ate_a_bill(self):
        """"Compras é o reino do assistente: ele leva as POs até as Bills."

        As duas linhas juntas são o processo inteiro — `purchase_user` grava
        o pedido E a fatura, `account_invoice` confirma. E o outro lado: ele
        NÃO administra compras nem vê contabilidade, senão "o assistente não
        vê relatórios" deixa de valer.
        """
        assistente = self.usuario['financeiro_assistente']
        self.assertTrue(assistente.has_group('purchase.group_purchase_user'))
        self.assertTrue(assistente.has_group('account.group_account_invoice'))
        for grupo in ('purchase.group_purchase_manager',
                      'account.group_account_readonly',
                      'liber_budget.group_budget_user',
                      'spreadsheet_dashboard.group_dashboard_manager'):
            self.assertFalse(
                assistente.has_group(grupo),
                'o assistente financeiro alcançou %s, e a régua era não ver '
                'relatório, painel nem saldo' % grupo)

    def test_o_editorial_edita_o_livro_no_metabooks(self):
        """"Acessa a metabooks e pode editar livros também."

        Antes de 11/08 o Editorial não tinha nada de Metabooks — quem fazia o
        livro não mexia no metadado dele.
        """
        self.assertTrue(
            self.usuario['editorial_assistente'].has_group(
                'liber_metabooks_integration.metabooks_product_group'))
        self.assertTrue(
            self.usuario['editorial_gerente'].has_group(
                'liber_metabooks_integration.metadata_group'))

    def test_o_marketing_nao_tem_nada_a_ver_com_consignacao(self):
        """A frase é literal, e o grupo saiu por migração em 11/08."""
        for nivel in ('assistente', 'gerente'):
            self.assertFalse(
                self.usuario['marketing_%s' % nivel].has_group(
                    'liber_soc_agreements.group_soc_user'),
                'o Marketing/%s voltou à consignação' % nivel)

    def test_o_juridico_manteve_a_analitica(self):
        """Perguntado e respondido em 11/08: fica. Fechar período de royalty
        é ler conta analítica, e quem fecha período é ele."""
        self.assertTrue(
            self.usuario['juridico_gerente'].has_group(
                'analytic.group_analytic_accounting'))

    def test_todo_gerente_aprova_a_despesa_da_equipe(self):
        """A divisão chefe/funcionário do comentário geral do PERFIS.md, que
        no Odoo se cumpre com UMA marcação — o resto vem da ficha de
        funcionário, não de grupo."""
        for dep in self.DEPARTAMENTOS:
            self.assertTrue(
                self.usuario['%s_gerente' % dep].has_group(
                    'hr_expense.group_hr_expense_team_approver'),
                'o gerente de %s não aprova despesa da equipe' % dep)
            self.assertFalse(
                self.usuario['%s_assistente' % dep].has_group(
                    'hr_expense.group_hr_expense_team_approver'),
                'o assistente de %s aprova despesa, e aprovar é de quem chefia'
                % dep)

    def test_o_rastreio_de_links_e_do_marketing(self):
        """"Link tracker é só para marketing" — 11/08/2026, nos dois níveis.

        Antes desta régua o menu era travado em `base.group_no_one`, o modo
        debug: a ferramenta existia e NINGUÉM a via, marketing inclusive.

        A asserção é sobre o menu de propósito, porque é só isso que a linha
        promete. O ACL do core dá `link.tracker` a todo usuário interno, e
        estreitá-lo quebraria o envio de e-mail de quem não é do Marketing —
        o `mail_render_mixin` cria link tracker ao renderizar. O porquê está
        no cabeçalho de security/menu_link_tracker.xml.
        """
        for nivel in ('assistente', 'gerente'):
            self._assert_menu('marketing_%s' % nivel,
                              'utm.menu_link_tracker_root',
                              'Link Tracker', visivel=True)

    def test_o_rastreio_de_links_nao_e_de_mais_ninguem(self):
        """O outro lado da régua, que é o que a torna uma régua."""
        for dep in ('comercial', 'logistica', 'financeiro', 'editorial',
                    'juridico'):
            for nivel in ('assistente', 'gerente'):
                self._assert_menu('%s_%s' % (dep, nivel),
                                  'utm.menu_link_tracker_root',
                                  'Link Tracker', visivel=False)
