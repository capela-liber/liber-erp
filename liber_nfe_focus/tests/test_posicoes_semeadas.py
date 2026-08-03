# -*- coding: utf-8 -*-
"""As posições fiscais nascem prontas, e as herdadas são adotadas.

O que se testa aqui não é a emissão -- é o cadastro que a emissão pressupõe. A
posição fiscal sem operação não estoura: ela emite a nota com o CFOP errado, em
silêncio, e o erro aparece semanas depois na apuração. Por isso o cadastro tem
teste próprio.

Os dois caminhos, separados de propósito:

  semeadura   banco novo, ou empresa nova: uma posição por operação, nome no
              formato da casa, operação ligada.
  adoção      banco migrado: as 111 posições que vieram do legado, onde o CFOP
              morava no nome porque não tinha outro lugar.
"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'focus_nfe')
class TestPosicoesSemeadas(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Posicao = cls.env['account.fiscal.position']
        cls.br = cls.env.ref('base.br')

        # As operações que o módulo entrega, com a letra que a casa lhes deu --
        # não cópias de teste. Se a letra do dado sair do lugar, é aqui que
        # aparece, e não na primeira nota.
        Operacao = cls.env['nfe.operacao']

        def operacao(code, sentido='saida'):
            op = Operacao.search(
                [('code', '=', code), ('sentido', '=', sentido)], limit=1)
            assert op, 'o módulo deveria entregar a operação %s/%s' % (
                sentido, code)
            return op

        cls.op_venda = operacao('101')          # (A) venda de produção
        cls.op_consig = operacao('917')         # (B) remessa em consignação
        cls.op_devolucao = operacao('202', 'entrada')   # (A) devolução de venda
        # Um sufixo que a casa não usa, para o caso sem letra: o alfabeto é
        # aberto e nem toda operação nova nasce com família.
        cls.op_sem_letra = Operacao.create({
            'code': '860', 'sentido': 'saida', 'name': 'Remessa de teste'})
        cls.operacoes = (cls.op_venda | cls.op_consig | cls.op_devolucao
                         | cls.op_sem_letra)

        # A empresa nasce sem país e só depois vira brasileira: assim ela NÃO é
        # semeada no `create`, e cada teste chama a semeadura que quer testar.
        cls.empresa = cls.env['res.company'].create({'name': 'Editora Teste'})
        cls.empresa.partner_id.country_id = cls.br

    def assertOperacoes(self, posicoes, operacoes):
        self.assertEqual(set(posicoes.mapped('nfe_operacao_id').ids),
                         set(operacoes.ids))

    def posicoes_da(self, empresa=None):
        return self.Posicao.with_context(active_test=False).search([
            ('company_id', '=', (empresa or self.empresa).id),
            ('nfe_operacao_id', 'in', self.operacoes.ids)])

    # ------------------------------------------------------- semeadura
    def test_semeia_uma_posicao_por_operacao_ja_ligada(self):
        """O caminho feliz: quatro operações, quatro posições, mapeadas."""
        self.Posicao._nfe_semear_posicoes(
            companies=self.empresa, operacoes=self.operacoes)
        posicoes = self.posicoes_da()
        self.assertEqual(len(posicoes), 4)
        self.assertOperacoes(posicoes, self.operacoes)
        # Mapeada quer dizer mapeada: nenhuma sai com a operação em branco.
        self.assertFalse(posicoes.filtered(lambda p: not p.nfe_operacao_id))

    def test_o_nome_traz_letra_operacao_e_o_par_de_cfops(self):
        self.Posicao._nfe_semear_posicoes(
            companies=self.empresa, operacoes=self.op_consig)
        posicao = self.posicoes_da()
        self.assertEqual(
            posicao.name, '(B) Remessa em consignacao mercantil — 5917/6917')

    def test_operacao_sem_letra_nao_ganha_parenteses_vazio(self):
        """A letra é opcional -- o alfabeto da casa não cobre tudo ainda."""
        self.Posicao._nfe_semear_posicoes(
            companies=self.empresa, operacoes=self.op_sem_letra)
        posicao = self.posicoes_da()
        self.assertEqual(posicao.name, 'Remessa de teste — 5860/6860')
        self.assertNotIn('()', posicao.name)

    def test_semear_duas_vezes_nao_duplica(self):
        """Idempotência: a chave é o par (empresa, operação)."""
        self.Posicao._nfe_semear_posicoes(
            companies=self.empresa, operacoes=self.operacoes)
        criadas = self.Posicao._nfe_semear_posicoes(
            companies=self.empresa, operacoes=self.operacoes)
        self.assertFalse(criadas)
        self.assertEqual(len(self.posicoes_da()), 4)

    def test_empresa_de_fora_do_brasil_nao_e_semeada(self):
        """A NFe é brasileira. Semear a Motor Portugal seria só sujeira."""
        estrangeira = self.env['res.company'].create({'name': 'Motor Lisboa'})
        estrangeira.partner_id.country_id = self.env.ref('base.pt')
        self.assertNotIn(estrangeira, self.Posicao._nfe_empresas_brasileiras())
        self.assertFalse(self.posicoes_da(estrangeira))

    def test_empresa_brasileira_nova_nasce_com_as_posicoes(self):
        """Criar a editora não pode exigir lembrar de rodar a semeadura."""
        nova = self.env['res.company'].create({
            'name': 'Editora Recem-Nascida',
            'country_id': self.br.id,
        })
        self.assertOperacoes(self.posicoes_da(nova), self.operacoes)

    # ---------------------------------------------------------- adoção
    def herdada(self, nome, empresa=None):
        """Uma posição como o legado a entregou: nome cheio, operação vazia."""
        return self.Posicao.create({
            'name': nome, 'company_id': (empresa or self.empresa).id})

    def test_adota_a_operacao_declarada_no_nome_e_limpa_o_nome(self):
        posicao = self.herdada(
            '(B) Remessa de consignação (EdLab Press)* CFOP: 5917/6917')
        self.Posicao._nfe_adotar_posicoes_do_legado()
        self.assertEqual(posicao.nfe_operacao_id, self.op_consig)
        self.assertEqual(posicao.name, '(B) Remessa de consignação — 5917/6917')

    def test_o_nome_perde_a_empresa_mas_guarda_a_letra_e_o_pf_pj(self):
        posicao = self.herdada(
            '(A) Venda de Produção PJ (Editora Hedra) CFOP: 5101/6101')
        self.Posicao._nfe_adotar_posicoes_do_legado()
        self.assertEqual(posicao.name, '(A) Venda de Produção PJ — 5101/6101')
        self.assertNotIn('Hedra', posicao.name)

    def test_nome_que_colidiria_e_mapeado_mas_nao_renomeado(self):
        """PF e PJ têm o mesmo CFOP: limpar as duas faria duas com o mesmo nome.

        O que se preserva aqui é a capacidade de escolher: duas posições com
        nome idêntico na mesma empresa transformam a escolha na fatura em
        adivinhação. Mapeia as duas, renomeia só a que dá.
        """
        ja_existe = '(A) Venda — 5101/6101'
        self.herdada(ja_existe).nfe_operacao_id = self.op_venda
        conflitante = self.herdada('(A) Venda (Editora Hedra) CFOP: 5101/6101')
        self.Posicao._nfe_adotar_posicoes_do_legado()
        self.assertEqual(conflitante.nfe_operacao_id, self.op_venda)
        self.assertEqual(
            conflitante.name, '(A) Venda (Editora Hedra) CFOP: 5101/6101')

    def test_a_letra_do_nome_herdado_cede_a_da_operacao(self):
        """A feira saiu como (E) e como (Z) no legado, no mesmo 5914/6914.

        Uma taxonomia em que a mesma operação tem duas letras não classifica
        nada. A letra passa a morar só na operação, e o nome a repete -- então
        adotar o nome herdado corrige a letra em vez de propagar a divergência.
        """
        feira = self.env['nfe.operacao'].search(
            [('code', '=', '914'), ('sentido', '=', 'saida')], limit=1)
        self.assertEqual(feira.letra, 'Z')
        posicao = self.herdada(
            '(E) Remessa para feiras e eventos (Editora Hedra)* CFOP: 5914/6914')
        self.Posicao._nfe_adotar_posicoes_do_legado()
        self.assertEqual(posicao.nfe_operacao_id, feira)
        self.assertEqual(
            posicao.name, '(Z) Remessa para feiras e eventos — 5914/6914')

    def test_nome_sem_cfop_dedutivel_fica_como_estava(self):
        """O caso de erro: 1917 pede uma entrada 917 que a casa não tem.

        É a "(C) Devolução simbólica de terceiros CFOP: 1917" da Hedra -- que a
        n-1 emitiu 18 vezes como saída 5919. Não inventamos a operação: a
        posição fica intocada e sai no relatório da migração.
        """
        posicao = self.herdada(
            '(C) Devolução simbólica de terceiros (Editora Hedra) CFOP: 1917')
        _adotadas, _renomeadas, sem_operacao = (
            self.Posicao._nfe_adotar_posicoes_do_legado())
        self.assertIn(posicao, sem_operacao)
        self.assertFalse(posicao.nfe_operacao_id)
        self.assertEqual(
            posicao.name,
            '(C) Devolução simbólica de terceiros (Editora Hedra) CFOP: 1917')

    def test_nome_sem_cfop_nenhum_nao_e_tocado(self):
        posicao = self.herdada('DIREITOS AUTORAIS (IRRF)')
        self.Posicao._nfe_adotar_posicoes_do_legado()
        self.assertFalse(posicao.nfe_operacao_id)
        self.assertEqual(posicao.name, 'DIREITOS AUTORAIS (IRRF)')

    def test_posicao_ja_mapeada_a_mao_nao_e_mexida(self):
        posicao = self.herdada('Remessa em consignacao')
        posicao.nfe_operacao_id = self.op_consig
        self.Posicao._nfe_adotar_posicoes_do_legado()
        self.assertEqual(posicao.name, 'Remessa em consignacao')

    def test_adotar_antes_de_semear_nao_gera_a_segunda_posicao(self):
        """A ordem do hook: adota, depois semeia. A adotada ocupa o lugar."""
        self.herdada('(B) Remessa de consignação (Hedra)* CFOP: 5917/6917')
        self.Posicao._nfe_adotar_posicoes_do_legado()
        self.Posicao._nfe_semear_posicoes(
            companies=self.empresa, operacoes=self.op_consig)
        self.assertEqual(len(self.posicoes_da()), 1)

    # ------------------------------------------------- entrada e saída
    def test_o_sentido_sai_do_primeiro_digito_do_nome(self):
        """1202 é entrada; 5202 seria outra operação. O dígito decide."""
        posicao = self.herdada('(A) Devolução de venda (Hedra) CFOP: 1202/2202')
        self.Posicao._nfe_adotar_posicoes_do_legado()
        self.assertEqual(posicao.nfe_operacao_id, self.op_devolucao)
        self.assertEqual(posicao.name, '(A) Devolução de venda — 1202/2202')
