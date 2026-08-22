# -*- coding: utf-8 -*-
"""Jurídico: quem redige não assina, quem assina não configura.

A régua veio dita pela direção (05/08/2026) e tem três degraus, cada um com
o seu verbo: o Assistente LÊ o app inteiro e REDIGE minutas; o Gerente
ASSINA (valida, cancela, renova); a CONFIGURAÇÃO não é de nenhum dos dois --
é da Direção, exceção consciente à regra "gerente configura a própria área"
que vale nos outros departamentos.

O que este teste segura é a matemática dos implied_ids nos três degraus e,
no degrau de baixo, que "ler tudo" é verdade material: contrato, conta
analítica, relatório de royalty (analytic.line) e fatura (account.move)
abrem em leitura -- e continuam fechados para escrita.

Em 20/08/2026 o Gerente ganhou o que faltava para o acerto TERMINAR na mão de
quem o apura: *Financeiro: Faturamento* e *Compras: Usuário* (a nota do autor
é fatura de fornecedor, e o pedido que a origina é pedido de compra), Dropbox
e Drive no nível Gerente (o contrato assinado mora na nuvem) e o cadastro de
contato pela régua de nível. O Assistente não subiu junto em nada disso, e é
metade do que os testes daqui cobram.
"""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_roles')
class TestJuridico(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        company = cls.env.company

        def _usuario(nome, login, funcao):
            return Users.create({
                'name': nome, 'login': login,
                'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
                'group_ids': [(4, cls.env.ref('liber_roles.%s' % funcao).id)],
            })

        cls.assistente = _usuario('Jurídico Assistente',
                                  'juridico@liber.test',
                                  'group_juridico_assistente')
        cls.gerente = _usuario('Jurídico Gerente',
                               'juridico.gerente@liber.test',
                               'group_juridico_gerente')
        cls.direcao = _usuario('Direção', 'direcao.jur@liber.test',
                               'group_direcao')

        cls.author = cls.env['res.partner'].create({'name': 'Autora Teste'})
        cls.work = cls.env['product.template'].create({'name': 'Obra Teste'})
        cls.contract = cls.env['edlab.contract'].create({
            'company_id': company.id,
            'royalty_line_ids': [(0, 0, {
                'partner_id': cls.author.id,
                'product_id': cls.work.id,
                'tier_ids': [(0, 0, {
                    'qty_from': 0, 'qty_to': 0, 'percentage': 10.0})],
            })],
        })
        cls.env.flush_all()
        cls.env.registry.clear_cache()

    def _tem(self, user, xmlid):
        return user.has_group(xmlid)

    # -- a escada -----------------------------------------------------------

    def test_escada_de_grupos(self):
        """Assistente é user; Gerente é manager; Direção é config (e por
        implicação, tudo). Nenhum degrau vaza para cima."""
        user = 'liber_copyright_contracts.group_contract_user'
        manager = 'liber_copyright_contracts.group_contract_manager'
        config = 'liber_copyright_contracts.group_contract_config'

        self.assertTrue(self._tem(self.assistente, user))
        self.assertFalse(self._tem(self.assistente, manager))

        self.assertTrue(self._tem(self.gerente, manager))
        self.assertFalse(self._tem(self.gerente, config))

        self.assertTrue(self._tem(self.direcao, config))
        self.assertTrue(self._tem(self.direcao, manager))

    # -- assistente: lê tudo, redige, não assina ---------------------------

    def test_assistente_le_o_app_inteiro(self):
        for model in ('edlab.contract', 'account.analytic.account',
                      'account.analytic.line', 'account.move'):
            self.env[model].with_user(self.assistente).search([], limit=1)

    def test_assistente_redige_mas_nao_assina(self):
        Contract = self.env['edlab.contract'].with_user(self.assistente)
        minuta = Contract.create({'company_id': self.env.company.id})
        self.assertEqual(minuta.state, 'draft')
        with self.assertRaises(AccessError):
            minuta.action_validate()

    def test_assistente_nao_escreve_no_analitico(self):
        conta = self.env['account.analytic.account'].search([], limit=1)
        if not conta:
            self.skipTest('base sem conta analítica')
        with self.assertRaises(AccessError):
            conta.with_user(self.assistente).write({'name': 'X'})

    # -- gerente: assina ----------------------------------------------------

    def test_gerente_assina(self):
        contrato = self.contract.with_user(self.gerente)
        contrato.action_validate()
        self.assertEqual(contrato.state, 'valid')

    # -- gerente: o acerto termina em dinheiro (20/08/2026) ------------------

    def test_gerente_emite_a_nota_do_autor(self):
        """O quarto degrau, decidido em 20/08/2026.

        Quem apura o período passou a poder emitir o documento que sai da
        apuração: a nota do autor é uma fatura de fornecedor, e o pedido que a
        origina é um pedido de compra. Até aqui o Jurídico LIA `account.move`
        inteiro -- carona do `group_contract_user` -- e não escrevia linha
        nenhuma, então o documento tinha de ser digitado por outro
        departamento.

        Cobrado como ato, não como grupo: cria a Bill e a linha dentro dela.
        """
        env = self.env(user=self.gerente.id, su=False)
        fatura = env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.author.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Royalty do período',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })
        self.assertEqual(fatura.state, 'draft')
        self.assertTrue(fatura.id)

    def test_gerente_abre_o_pedido_de_compra(self):
        """*Compras: Usuário* -- o pedido que origina a nota do autor.

        O degrau de Administrador NÃO sobe junto: aprovar acima do limite e
        configurar compras seguem no Financeiro/Gerente.
        """
        env = self.env(user=self.gerente.id, su=False)
        pedido = env['purchase.order'].create({'partner_id': self.author.id})
        self.assertTrue(pedido.id)
        self.assertFalse(self._tem(self.gerente, 'purchase.group_purchase_manager'))

    def test_o_assistente_nao_sobe_junto(self):
        """Quem redige minuta não emite documento financeiro.

        Sem este lado a régua não é régua: seria só "o Jurídico ganhou
        faturamento", e o degrau entre redigir e assinar desapareceria.
        """
        for xmlid in ('account.group_account_invoice',
                      'purchase.group_purchase_user',
                      'liber_dropbox.group_liber_dropbox_manager',
                      'liber_gdrive.group_liber_gdrive_manager'):
            self.assertFalse(
                self._tem(self.assistente, xmlid),
                'o assistente jurídico carrega %s -- o degrau entre redigir e '
                'assinar sumiu' % xmlid)

    def test_gerente_administra_a_pasta_do_contrato(self):
        """Dropbox e Drive no nível GERENTE, não usuário (20/08/2026).

        O contrato assinado mora na nuvem, e quem assina responde pela pasta:
        cria e configura conta e pasta, não só usa a que o Editorial montou. O
        GitHub fica de fora de propósito -- lá mora código, não contrato.
        """
        for provedor in ('liber_dropbox', 'liber_gdrive'):
            self.assertTrue(
                self._tem(self.gerente, '%s.group_%s_manager' % (provedor, provedor)),
                '%s: o Jurídico/Gerente não administra a pasta' % provedor)
        # o Manager de cada provedor já implica o User dele e o gerente do
        # chassi; se essa aresta cair, a promessa "administra" fica pela metade
        self.assertTrue(self._tem(self.gerente,
                                  'liber_cloud_files.group_liber_cloud_manager'))
        self.assertFalse(
            self._tem(self.gerente, 'liber_github.group_liber_github_manager'),
            'o Jurídico ganhou o GitHub: lá mora código, não contrato')

    def test_gerente_cadastra_contato(self):
        """A régua do nível (20/08/2026): todo Gerente cadastra, todo
        Assistente lê. Aqui os dois lados, no mesmo departamento."""
        env = self.env(user=self.gerente.id, su=False)
        self.assertTrue(env['res.partner'].create({'name': 'Autor novo'}).id)

        env = self.env(user=self.assistente.id, su=False)
        self.assertEqual(
            env['res.partner'].browse(self.author.id).name, 'Autora Teste',
            'o assistente jurídico não lê contato')
        with self.assertRaises(AccessError):
            env['res.partner'].create({'name': 'Autor proibido'})
