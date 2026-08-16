# -*- coding: utf-8 -*-
"""A opção Venda do assistente: pedido de venda, e nenhuma CO.

Pedida pela direção em 12/08/2026 (issue #73). O que estes testes travam não é
"cria um pedido" -- é o que a torna diferente das outras três opções e o que
foi decidido explicitamente: preço de CAPA (não o do e-mail), desconto do
CADASTRO do cliente, e o acordo de consignação fora do caminho.
"""
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestVendaPeloAtendimento(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Num banco recém-instalado, DUAS opções de que estes testes dependem
        # vêm desligadas, e sem elas os testes falham sem que nada no módulo
        # esteja errado — no `testing` a casa as liga por seed (a segunda é o
        # padrão do liber_partner_commercial), mas o teste não pode depender
        # do banco:
        # - "Listas de preço": desligada, o Odoo devolve lista nenhuma para
        #   todo parceiro (`_get_partner_pricelist_multi` corta no
        #   `_is_feature_enabled`) e o pedido sai sem lista e sem desconto;
        # - "Descontos" (`group_discount_per_so_line`): desligada, o 55% é
        #   DOBRADO no preço (price_unit=45, discount=0) em vez de aparecer
        #   na coluna — e "preço de capa + coluna de desconto" é justamente
        #   o comportamento que se veio travar.
        # Ligar aqui é o mesmo gesto dos toggles nas Definições: os grupos
        # viram implied do group_user.
        cls.env.ref('base.group_user').implied_ids += (
            cls.env.ref('product.group_product_pricelist')
            + cls.env.ref('sale.group_discount_per_so_line'))
        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria do Desconto',
            'email': 'desconto@livraria.test',
            'allow_consignment': True,
        })
        # O desconto do cliente NESTA CASA é a lista de preço: 131 listas e
        # 11.595 clientes com lista própria no staging. A primeira versão
        # inventou um campo de percentual no parceiro e ignorou tudo isso --
        # o pedido saía 0% para quem tem "55% EL" na ficha.
        cls.lista = cls.env['product.pricelist'].create({
            'name': '55% teste',
            'item_ids': [(0, 0, {
                'applied_on': '3_global',
                'compute_price': 'percentage',
                'percent_price': 55.0,
            })],
        })
        cls.partner.specific_property_product_pricelist = cls.lista
        cls.team = cls.env['liber.support.team'].create({
            'name': 'Comercial Venda',
            'company_id': cls.env.company.id,
            'alias_name': 'venda-test',
        })
        cls.livro = cls.env['product.product'].create({
            'name': 'Livro de Capa', 'type': 'consu', 'is_storable': True,
            'list_price': 100.0, 'sale_ok': True,
        })
        cls.Ticket = cls.env['liber.support.ticket']

    def _assistente(self, dest='sale', preco_do_email=None, qty=3):
        ticket = self.Ticket.create({
            'name': 'Quero comprar', 'team_id': self.team.id,
            'partner_id': self.partner.id,
        })
        wizard = self.env['liber.support.co.wizard'].create({
            'ticket_id': ticket.id, 'default_dest': dest,
        })
        self.env['liber.support.co.wizard.line'].create({
            'wizard_id': wizard.id, 'product_id': self.livro.id, 'qty': qty,
        })
        return ticket, wizard

    def test_venda_cria_pedido_e_nenhuma_co(self):
        """O corte que dá nome à opção."""
        ticket, wizard = self._assistente()
        wizard.action_create_co()

        self.assertTrue(ticket.sale_order_id, "não criou pedido de venda")
        self.assertFalse(ticket.settlement_id,
                         "criou uma CO numa opção que não devia criar")
        self.assertEqual(len(ticket.sale_order_id.order_line), 1)

    def test_preco_e_o_de_capa_e_o_desconto_vem_da_lista(self):
        """As duas metades do preço, e é aqui que o dinheiro mora.

        O e-mail do cliente traz o preço que ele lembra, o que pagou da última
        vez ou o que gostaria de pagar. O preço da casa é o da ficha, e o
        abatimento é o da lista do cliente.

        A primeira versão escrevia `price_unit` e `discount` à mão e o pedido
        saía com 0% para um cliente com "55% EL" cadastrado: valor escrito
        vence valor computado, e a lista era ignorada em silêncio.
        """
        ticket, wizard = self._assistente()
        wizard.action_create_co()

        pedido = ticket.sale_order_id
        self.assertEqual(pedido.pricelist_id, self.lista,
                         "o pedido não pegou a lista do cliente")
        linha = pedido.order_line
        self.assertEqual(linha.price_unit, 100.0,
                         "o preço não é o de capa do produto")
        self.assertEqual(linha.discount, 55.0,
                         "o desconto não veio da lista de preço do cliente")
        self.assertEqual(linha.product_uom_qty, 3)

    def test_cliente_sem_desconto_sai_com_zero(self):
        """A borda: cliente cuja lista não dá desconto.

        E uma correção de premissa que este teste custou: NÃO existe "cliente
        sem lista de preço". Limpando a lista específica, o Odoo cai numa
        padrão -- o teste anterior zerava o campo e continuava recebendo 55%,
        porque a padrão da base era justamente a de teste. O caso real é a
        lista existir e não ter regra de desconto.
        """
        sem_desconto = self.env['product.pricelist'].create(
            {'name': 'Sem desconto (teste)'})
        self.partner.specific_property_product_pricelist = sem_desconto
        ticket, wizard = self._assistente()
        wizard.action_create_co()

        linha = ticket.sale_order_id.order_line
        self.assertEqual(linha.discount, 0.0)
        self.assertEqual(linha.price_unit, 100.0)

    def test_a_venda_ignora_o_acordo_de_consignacao(self):
        """Venda não lê CA, mesmo quando ele existe e tem desconto próprio.

        Sem este teste, "não considera o CA" fica sendo uma frase no commit.
        Com ele, misturar as duas condições comerciais fica vermelho.
        """
        self.env['consignment.agreement'].create({
            'partner_id': self.partner.id, 'discount': 55.0,
        })
        ticket, wizard = self._assistente()
        wizard.action_create_co()

        self.assertEqual(
            ticket.sale_order_id.order_line.discount, 55.0,
            "o desconto veio do acordo de consignação, não da lista do cliente")

    def test_as_tres_opcoes_antigas_continuam_criando_co(self):
        """O outro lado: a opção nova não pode ter mexido nas que existiam."""
        ticket, wizard = self._assistente(dest='sold')
        wizard.action_create_co()

        self.assertTrue(ticket.settlement_id, "a CO deixou de ser criada")
        self.assertFalse(ticket.sale_order_id,
                         "a opção de acerto criou pedido de venda")

    # ------------------------------------------------------------------
    # Chamado sem cliente: o caso que apareceu na tela (13/08/2026)
    # ------------------------------------------------------------------
    def test_sem_cliente_a_mensagem_fala_do_documento_certo(self):
        """A recusa dizia "a CO precisa do cliente" mesmo na Venda.

        Quem escolheu Venda e leu "CO" procura o erro no lugar errado. E a
        recusa chegava só no clique final, depois de ler a planilha inteira e
        escolher a opção.
        """
        from odoo.exceptions import UserError
        ticket = self.Ticket.create({
            'name': 'Sem cliente', 'team_id': self.team.id})
        # `lang='en_US'` de propósito: o que se testa é QUAL DOCUMENTO a
        # recusa nomeia, e a comparação é com o texto-fonte. Sem fixar o
        # idioma, o teste passa a depender do pt_BR estar traduzido naquele
        # dia -- e foi exatamente assim que ele ficou vermelho quando a
        # tradução entrou (13/08/2026), sem nada de errado no código.
        wizard = self.env['liber.support.co.wizard'].with_context(
            lang='en_US').create({
                'ticket_id': ticket.id, 'default_dest': 'sale'})
        self.env['liber.support.co.wizard.line'].create({
            'wizard_id': wizard.id, 'product_id': self.livro.id, 'qty': 1})

        with self.assertRaises(UserError) as erro:
            wizard.action_create_co()
        mensagem = str(erro.exception)
        self.assertIn('sale order', mensagem,
                      "na Venda a mensagem tem de falar em pedido, não em CO")
        self.assertNotIn('consignment settlement', mensagem)

        wizard.default_dest = 'sold'
        with self.assertRaises(UserError) as erro:
            wizard.action_create_co()
        self.assertIn('consignment settlement', str(erro.exception),
                      "no acerto a mensagem tem de falar em CO")

    def test_o_cliente_pode_ser_resolvido_no_proprio_assistente(self):
        """O atrito real: sem isto, é fechar tudo e voltar.

        O campo era só leitura, e um chamado sem cliente (e-mail de remetente
        que ninguém casou ainda) obrigava a sair do assistente, achar o
        chamado, preencher e voltar -- com 43 linhas de planilha na tela.
        """
        ticket = self.Ticket.create({
            'name': 'Sem cliente ainda', 'team_id': self.team.id})
        wizard = self.env['liber.support.co.wizard'].create({
            'ticket_id': ticket.id, 'default_dest': 'sale'})

        wizard.partner_id = self.partner

        self.assertEqual(ticket.partner_id, self.partner,
                         "preencher no assistente tem de gravar no chamado")
