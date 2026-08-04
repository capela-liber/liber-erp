# -*- coding: utf-8 -*-
"""A configuração fiscal vive no código, e sobrevive à reinstalação.

O ponto destes testes é o que motivou mudar de script para dado de módulo:
"terei que levar tudo isso para o staging depois e temo enxugar gelo". Se a
configuração se refaz a cada migração, ela não é configuração, é retrabalho.
"""

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'focus_nfe')
class TestConfigNoCodigo(AccountTestInvoicingCommon):

    chart_template = 'generic_coa'

    def test_operacoes_do_modulo_chegam_configuradas(self):
        """Instalado o módulo, as operações já sabem virar nota."""
        op = self.env.ref('liber_nfe_focus.operacao_saida_917',
                          raise_if_not_found=False)

        self.assertTrue(op, "A operação de saída 917 devia vir com o módulo")
        self.assertEqual(op.code, '917')
        self.assertEqual(op.sentido, 'saida')
        self.assertEqual(op.natureza_operacao, 'Remessa em consignacao mercantil')
        self.assertEqual(op.ibs_cbs_cst, '410')
        self.assertEqual(op.ibs_cbs_classificacao, '410008')
        self.assertEqual(op.cbenef, 'SP070130')

    def test_uma_operacao_serve_dentro_e_fora_do_estado(self):
        """O ponto do modelo: 5917 e 6917 são a MESMA operação. Antes eram duas
        linhas com a mesma configuração escrita duas vezes."""
        op = self.env.ref('liber_nfe_focus.operacao_saida_917')

        self.assertEqual(op.cfop_para('interna'), '5917')
        self.assertEqual(op.cfop_para('interestadual'), '6917')
        # Exportação não se deduz: lá o código significa outra coisa.
        self.assertIsNone(op.cfop_para('exterior'))

    def test_sufixo_igual_em_sentidos_diferentes_sao_operacoes_diferentes(self):
        """918 na saída é devolver o que recebemos em consignação; na entrada é
        receber de volta o que remetemos."""
        saida = self.env.ref('liber_nfe_focus.operacao_saida_918')
        entrada = self.env.ref('liber_nfe_focus.operacao_entrada_918')

        self.assertNotEqual(saida, entrada)
        self.assertEqual(saida.cfop_para('interna'), '5918')
        self.assertEqual(entrada.cfop_para('interna'), '1918')

    def test_devolucao_ja_vem_com_finalidade_4(self):
        """Devolução emitida como normal é rejeitada — e isso não pode depender
        de alguém lembrar de configurar."""
        for xmlid in ('operacao_entrada_918', 'operacao_saida_919',
                      'operacao_entrada_202'):
            op = self.env.ref('liber_nfe_focus.%s' % xmlid,
                              raise_if_not_found=False)
            self.assertTrue(op, "Faltou %s" % xmlid)
            self.assertEqual(op.finalidade, '4',
                             "%s é devolução e tem de sair com finalidade 4" % xmlid)

    def test_natureza_nao_carrega_o_nome_da_empresa(self):
        """O DANFE já traz o emitente no cabeçalho."""
        empresas = ('EdLab', 'Hedra', 'n-1', 'Saíra', 'Press')
        for op in self.env['nfe.operacao'].search([]):
            for nome in empresas:
                self.assertNotIn(nome, op.natureza_operacao or '',
                                 "%s ainda tem '%s' na natureza" % (op.code, nome))

    def test_cfop_sem_operacao_configurada_existe_mas_nao_vira_nota(self):
        """A tabela oficial traz os 619; a configuração cobre só o que a casa
        emite.

        Note que a pergunta mudou de forma com o modelo novo: `6102` passou a
        ter operação, porque a operação é o SUFIXO (102) e o 5102 está
        configurado. É o ponto do desenho — configurar uma vez serve para
        dentro e para fora do estado. Quem fica sem operação é o sufixo que
        ninguém configurou.

        Os exemplos são de propósito coisas que uma editora não faz: vender
        ativo imobilizado, comprar material de consumo, faturar para entrega
        futura. Os três de antes (5209, 6209, 1914) saíram daqui quando
        passaram a ser configurados de verdade — eram justamente as operações
        que doze posições fiscais herdadas do legado estavam pedindo.
        """
        for codigo in ('5551', '6551', '1556', '1922'):
            cfop = self.env['nfe.cfop'].search([('code', '=', codigo)], limit=1)
            self.assertTrue(cfop, "O CFOP %s devia existir (tabela oficial)" % codigo)
            self.assertTrue(cfop.name, "O CFOP %s devia ter descrição oficial" % codigo)
            self.assertFalse(
                cfop._operacao(),
                "O sufixo de %s não foi configurado e não devia ter operação" % codigo)

    def test_configurar_uma_vez_serve_para_os_dois_destinos(self):
        """O 6102 nunca foi configurado à mão: ele herda do 102."""
        interno = self.env['nfe.cfop'].search([('code', '=', '5102')], limit=1)
        externo = self.env['nfe.cfop'].search([('code', '=', '6102')], limit=1)

        self.assertTrue(interno._operacao())
        self.assertEqual(interno._operacao(), externo._operacao())

    # -- geração dos impostos ------------------------------------------
    def test_botao_gera_um_imposto_por_cfop(self):
        company = self.env.company
        company.focus_regime_tributario = '3'

        company.action_focus_gerar_impostos()

        impostos = self.env['account.tax'].search([
            ('company_id', '=', company.id), ('nfe_operacao_id', '!=', False)])
        cfops = self.env['nfe.operacao'].search([])
        # Por CÓDIGO distinto, não por registro: um banco que já rodou scripts
        # avulsos pode ter dois CFOPs com o mesmo código, e o imposto é um só
        # por código -- que é o comportamento certo.
        self.assertEqual(len(impostos), len(cfops))
        # Alíquota zero: ele marca a operação, não tributa.
        self.assertEqual(set(impostos.mapped('amount')), {0.0})
        # Pelo par (sufixo, sentido), não pelo sufixo: 917 e 918 existem nos
        # dois sentidos -- remeter em consignação e receber de volta são
        # operações diferentes com o mesmo sufixo. Filtrar só pelo código traz
        # duas e estoura em `consig.name` com "Expected singleton".
        consig = impostos.filtered(
            lambda t: (t.nfe_operacao_id.code == '917'
                       and t.nfe_operacao_id.sentido == 'saida'))
        self.assertEqual(len(consig), 1)
        self.assertIn('OP x917', consig.name)
        self.assertIn('ICMS 41', consig.name)

    def test_gerar_duas_vezes_nao_duplica(self):
        """Idempotente, porque vai rodar de novo a cada migração."""
        company = self.env.company
        company.action_focus_gerar_impostos()
        antes = self.env['account.tax'].search_count([
            ('company_id', '=', company.id), ('nfe_operacao_id', '!=', False)])

        company.action_focus_gerar_impostos()

        depois = self.env['account.tax'].search_count([
            ('company_id', '=', company.id), ('nfe_operacao_id', '!=', False)])
        self.assertEqual(antes, depois)

    def test_simples_nacional_gera_csosn_e_nao_cst(self):
        company = self.env.company
        company.focus_regime_tributario = '1'

        company.action_focus_gerar_impostos()

        imposto = self.env['account.tax'].search([
            ('company_id', '=', company.id), ('nfe_operacao_id.code', '=', '917')], limit=1)
        self.assertIn('ICMS 400', imposto.name)

    # -- a tabela oficial ----------------------------------------------
    def test_cfop_traz_a_descricao_oficial_do_confaz(self):
        """`name` é a descrição normativa do Anexo II do Convênio SINIEF s/nº,
        e não se inventa. Ela é DIFERENTE da natureza que vai no DANFE."""
        cfop = self.env['nfe.cfop'].search([('code', '=', '5917')], limit=1)

        self.assertEqual(
            cfop.name,
            'Remessa de mercadoria em consignação mercantil ou industrial')
        # A natureza é nossa, mais curta, e mora na OPERAÇÃO — não no CFOP.
        self.assertEqual(cfop._operacao().natureza_operacao,
                         'Remessa em consignacao mercantil')

    def test_a_tabela_oficial_veio_inteira(self):
        """619 códigos, das seis faixas (1,2,3 entradas; 5,6,7 saídas)."""
        cfops = self.env['nfe.cfop'].search([('name', '!=', False)])

        self.assertGreater(len(cfops), 600)
        self.assertEqual(sorted({c.code[0] for c in cfops if c.code}),
                         ['1', '2', '3', '5', '6', '7'])

    def test_nenhum_cfop_fica_sem_descricao(self):
        """Os 7 sem nome vinham do classify_cfops, que grava só o código."""
        sem_nome = self.env['nfe.cfop'].search(
            ['|', ('name', '=', False), ('name', '=', '')])

        self.assertFalse(sem_nome, "sem descrição: %s" % sem_nome.mapped('code'))

    def test_codigo_e_unico_no_banco(self):
        """A unicidade é garantida pelo Postgres, não por um `constrains`.

        O teste olha o catálogo em vez de tentar violar a regra: violar uma
        constraint aborta a transação do teste, e o que importa aqui é que a
        garantia EXISTA -- se ela existe, o banco não deixa passar.
        """
        self.env.cr.execute("""
            SELECT c.conname, pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            WHERE t.relname = 'nfe_cfop' AND c.contype = 'u'
        """)
        constraints = self.env.cr.fetchall()

        self.assertTrue(
            any('code' in definicao for _nome, definicao in constraints),
            "nfe_cfop devia ter unicidade em code; achei: %s" % (constraints,))

    def test_nao_ha_codigo_repetido_no_banco(self):
        """O que a constraint garante daqui para frente, e a instalação
        arrumou para trás."""
        self.env.cr.execute(
            "SELECT code FROM nfe_cfop GROUP BY code HAVING count(*) > 1")

        self.assertFalse(self.env.cr.fetchall())
