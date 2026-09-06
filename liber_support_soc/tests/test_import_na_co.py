# -*- coding: utf-8 -*-
"""O atendimento ATIVO: o assistente aberto DA CO (01/09/2026).

O reativo já estava provado — chega um e-mail, o chamado vira documento. O
ativo anda no sentido contrário: parte-se da CO da livraria, escreve-se para
ela, e a resposta volta para DENTRO daquela CO. O mecanismo é o mesmo; o que
estes testes travam é o que muda ao trocar a âncora:

* as linhas caem NA CO de onde o assistente foi aberto, e nenhuma segunda CO
  nasce;
* elas **somam** na linha do título que já está no mapa, em vez de duplicá-lo
  — a CO do atendimento ativo em geral já veio do `action_populate_from_shelf`,
  e uma segunda linha do mesmo livro contaria duas vezes o que a livraria
  vendeu uma;
* a CO já rodada recusa a importação: dali em diante ela é o mapa que o
  cliente recebeu.
"""
import base64

from markupsafe import Markup

from odoo.exceptions import UserError, ValidationError
from odoo.tests import common, tagged

from ..models import co_parser

CNPJ_LIVRARIA = '11222333000181'
CNPJ_CASA = '99888777000166'

NFE_XML = ('''<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
 <NFe><infNFe Id="NFe35240811222333000181550010000012341000012349">
  <emit><CNPJ>%s</CNPJ><xNome>Livraria Ativa</xNome></emit>
  <dest><CNPJ>%s</CNPJ><xNome>EdLab</xNome></dest>
  <det nItem="1"><prod>
    <cProd>INT-1</cProd><cEAN>9788577151234</cEAN>
    <xProd>Fim do SUS?</xProd><qCom>4.0000</qCom>
  </prod></det>
 </infNFe></NFe>
</nfeProc>''' % (CNPJ_LIVRARIA, CNPJ_CASA)).encode()


@tagged('post_install', '-at_install')
class TestImportNaCo(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria Ativa', 'is_company': True,
            'vat': CNPJ_LIVRARIA, 'allow_consignment': True,
        })
        cls.env['consignment.agreement'].create({
            'partner_id': cls.partner.id,
        })
        cls.livro = cls.env['product.product'].create({
            'name': 'Fim do SUS?', 'type': 'consu', 'is_storable': True,
            'barcode': '9788577151234', 'list_price': 80.0, 'sale_ok': True,
        })
        cls.outro = cls.env['product.product'].create({
            'name': 'Banguela', 'type': 'consu', 'is_storable': True,
            'barcode': '9786589705468', 'list_price': 60.0, 'sale_ok': True,
        })
        cls.Wizard = cls.env['liber.support.co.wizard']

    @staticmethod
    def _email(corpo):
        """`message_post` ESCAPA um `body` que seja str puro — o
        `<p>` viraria `&lt;p&gt;` e o parser leria a tag como se fosse
        título, com quantidade 1. E-mail de verdade chega como HTML, então
        o teste tem de postar `Markup`. Custou um `1 != 2`."""
        return Markup(corpo)

    def _co(self):
        return self.env['consignment.settlement'].create({
            'partner_id': self.partner.id,
        })

    # -- caminho feliz -------------------------------------------------

    def test_importa_da_conversa_da_co(self):
        """A resposta da livraria no chatter da CO vira linha DELA."""
        co = self._co()
        co.message_post(body=self._email('<p>3 Fim do SUS?<br/>2 Banguela</p>'),
                        message_type='email',
                        subtype_xmlid='mail.mt_comment')
        co.action_open_co_wizard()
        wizard = self.Wizard.search([('settlement_id', '=', co.id)])
        self.assertEqual(len(wizard), 1, "o rascunho não nasceu na CO")
        self.assertFalse(wizard.ticket_id, "nasceu preso a um chamado")
        self.assertEqual(wizard.partner_id, self.partner,
                         "o cliente não veio da CO")
        self.assertEqual(len(wizard.line_ids), 2, wizard.source_text)

        wizard.action_create_co()
        self.assertEqual(len(co.line_ids), 2)
        self.assertEqual(
            co.line_ids.filtered(
                lambda l: l.product_id == self.livro).qty_reported, 3)
        # nenhuma segunda CO: o documento é o de onde se partiu
        self.assertEqual(
            self.env['consignment.settlement'].search_count(
                [('partner_id', '=', self.partner.id)]), 1)
        # e o rascunho cumprido some
        self.assertFalse(wizard.exists())

    def test_soma_na_linha_que_ja_esta_no_mapa(self):
        """A CO do atendimento ativo já vem com o mapa da prateleira: o
        título importado soma na linha dele, não abre uma segunda."""
        co = self._co()
        self.env['consignment.settlement.line'].create({
            'settlement_id': co.id, 'product_id': self.livro.id,
            'qty_reported': 1,
        })
        co.action_open_co_wizard()
        wizard = self.Wizard.search([('settlement_id', '=', co.id)])
        wizard.source_text = '3 Fim do SUS?'
        wizard.action_parse()
        wizard.action_create_co()

        linha = co.line_ids
        self.assertEqual(len(linha), 1, "duplicou o título que já estava lá")
        self.assertEqual(linha.qty_reported, 4, "não somou no que já havia")

    def test_reabrir_devolve_o_mesmo_rascunho(self):
        """Um rascunho por CO: sair para conferir algo não custa o
        trabalho já feito."""
        co = self._co()
        co.action_open_co_wizard()
        wizard = self.Wizard.search([('settlement_id', '=', co.id)])
        wizard.source_text = '2 Banguela'
        wizard.action_parse()
        co.action_open_co_wizard()
        de_novo = self.Wizard.search([('settlement_id', '=', co.id)])
        self.assertEqual(de_novo, wizard, "abriu um segundo rascunho")
        self.assertEqual(de_novo.line_ids.product_id, self.outro,
                         "o rascunho voltou sem o trabalho feito")

    def test_reposicao_cai_na_coluna_certa(self):
        """O destino escolhido na tela manda na COLUNA da linha da CO."""
        co = self._co()
        co.action_open_co_wizard()
        wizard = self.Wizard.search([('settlement_id', '=', co.id)])
        wizard.write({'source_text': '5 Banguela',
                      'default_dest': 'replenish'})
        wizard.action_parse()
        wizard.action_create_co()
        self.assertEqual(co.line_ids.qty_replenish, 5)
        self.assertEqual(co.line_ids.qty_reported, 0)

    # -- edge: o XML de NFe, que é a fonte exata ------------------------

    def test_xml_vence_o_texto_tambem_na_co(self):
        """Com XML anexado na CO, o texto do e-mail não soma linha por
        cima — e a quantidade é a da SEFAZ."""
        co = self._co()
        co.message_post(body=self._email('<p>99 Banguela</p>'),
                        message_type='email',
                        subtype_xmlid='mail.mt_comment')
        self.env['ir.attachment'].create({
            'name': 'nota.xml', 'res_model': 'consignment.settlement',
            'res_id': co.id, 'datas': base64.b64encode(NFE_XML),
        })
        co.action_open_co_wizard()
        wizard = self.Wizard.search([('settlement_id', '=', co.id)])
        self.assertTrue(wizard.attachment_id, "não pegou o XML da CO")
        self.assertEqual(len(wizard.line_ids), 1,
                         "o texto do e-mail somou por cima do XML")
        self.assertEqual(wizard.line_ids.product_id, self.livro)
        self.assertEqual(wizard.line_ids.qty, 4)
        # o CNPJ da CO é o emitente da nota: nada a gritar
        self.assertFalse(wizard.cnpj_alert)

    def test_cnpj_de_outra_livraria_grita_e_barra(self):
        outra = self.env['res.partner'].create({
            'name': 'Livraria Errada', 'is_company': True,
            'vat': '12345678000195', 'allow_consignment': True,
        })
        self.env['consignment.agreement'].create({'partner_id': outra.id})
        co = self.env['consignment.settlement'].create({
            'partner_id': outra.id,
        })
        self.env['ir.attachment'].create({
            'name': 'nota.xml', 'res_model': 'consignment.settlement',
            'res_id': co.id, 'datas': base64.b64encode(NFE_XML),
        })
        co.action_open_co_wizard()
        wizard = self.Wizard.search([('settlement_id', '=', co.id)])
        self.assertTrue(wizard.cnpj_alert, "o XML de outra livraria passou")
        with self.assertRaises(UserError):
            wizard.action_create_co()
        wizard.cnpj_override = True
        wizard.action_create_co()
        self.assertTrue(co.line_ids, "o override não deixou criar")

    def test_venda_pela_co_nao_toca_no_acerto(self):
        """A opção Venda vale nas duas âncoras — mas o pedido firme NÃO
        vira o pedido do acerto da CO."""
        co = self._co()
        co.action_open_co_wizard()
        wizard = self.Wizard.search([('settlement_id', '=', co.id)])
        wizard.write({'source_text': '2 Banguela', 'default_dest': 'sale'})
        wizard.action_parse()
        action = wizard.action_create_co()
        self.assertEqual(action['res_model'], 'sale.order')
        pedido = self.env['sale.order'].browse(action['res_id'])
        self.assertEqual(pedido.origin, co.name,
                         "o pedido saiu sem a CO na origem")
        self.assertFalse(co.sale_order_id,
                         "a venda firme virou o pedido do acerto da CO")
        self.assertFalse(co.line_ids, "a venda mexeu nas linhas da CO")

    def test_a_venda_rara_deixa_link_nos_dois_chatters(self):
        """A Venda saída de uma CO é rara e NÃO tem campo que a guarde: a CO
        já usa `sale_order_id` para o pedido do acerto. Sem campo, a única
        trilha é o chatter — e um número em texto obriga a copiar e caçar na
        lista. Pedido do usuário em 01/09/2026: link nos dois lados."""
        co = self._co()
        co.action_open_co_wizard()
        wizard = self.Wizard.search([('settlement_id', '=', co.id)])
        wizard.write({'source_text': '2 Banguela', 'default_dest': 'sale'})
        wizard.action_parse()
        action = wizard.action_create_co()
        pedido = self.env['sale.order'].browse(action['res_id'])

        # ida: o chatter da CO leva ao pedido
        nota_co = co.message_ids.filtered(
            lambda m: 'Sale order' in str(m.body)
            or 'Pedido de venda' in str(m.body))[:1]
        self.assertTrue(nota_co, "a CO não registrou a venda")
        corpo = str(nota_co.body)
        self.assertIn('data-oe-model="sale.order"', corpo,
                      "o número do pedido saiu como texto, sem link")
        self.assertIn('data-oe-id="%s"' % pedido.id, corpo)

        # volta: o pedido guarda a CO só no `origin`, que é texto solto
        nota_pedido = pedido.message_ids.filtered(
            lambda m: 'data-oe-model="consignment.settlement"'
            in str(m.body))[:1]
        self.assertTrue(nota_pedido,
                        "o pedido não aponta de volta para a CO")
        self.assertIn('data-oe-id="%s"' % co.id, str(nota_pedido.body))

    # -- casos de erro -------------------------------------------------

    def test_co_ja_rodada_recusa_importacao(self):
        co = self._co()
        co.state = 'confirmed'
        with self.assertRaises(UserError):
            co.action_open_co_wizard()

    def test_rascunho_sem_ancora_ou_com_as_duas_e_recusado(self):
        co = self._co()
        team = self.env['liber.support.team'].create({
            'name': 'Comercial Ativo', 'company_id': self.env.company.id,
            'alias_name': 'ativo-test',
        })
        ticket = self.env['liber.support.ticket'].create({
            'name': 'Conversa', 'team_id': team.id,
            'partner_id': self.partner.id,
        })
        with self.assertRaises(ValidationError):
            self.Wizard.create({})
        with self.assertRaises(ValidationError):
            self.Wizard.create({
                'ticket_id': ticket.id, 'settlement_id': co.id})

    def test_devolucao_sem_prateleira_esbarra_na_guarda_do_soc(self):
        """O assistente não é um atalho por fora das regras da consignação:
        devolver o que não está na prateleira continua sendo recusado, pela
        mesma constraint que recusa a digitação à mão."""
        co = self._co()
        co.action_open_co_wizard()
        wizard = self.Wizard.search([('settlement_id', '=', co.id)])
        wizard.write({'source_text': '5 Banguela', 'default_dest': 'return'})
        wizard.action_parse()
        with self.assertRaises(ValidationError):
            wizard.action_create_co()

    def test_venda_nao_vaza_para_a_coluna_de_destino_da_linha(self):
        """`sale` é outro DOCUMENTO, não um destino de linha. Na tela o
        onchange já o segurava; pelo ORM ele chegava ao INSERT da grade e
        estourava — caminho que passou a ser exercitado quando a CO virou
        âncora."""
        co = self._co()
        co.action_open_co_wizard()
        wizard = self.Wizard.search([('settlement_id', '=', co.id)])
        wizard.write({'source_text': '2 Banguela', 'default_dest': 'sale'})
        wizard.action_parse()
        self.assertEqual(wizard.line_ids.dest, 'sold')

    def test_linha_sem_produto_nao_entra(self):
        co = self._co()
        co.action_open_co_wizard()
        wizard = self.Wizard.search([('settlement_id', '=', co.id)])
        wizard.source_text = 'Livro Que Nao Existe No Catalogo Nenhum'
        wizard.action_parse()
        with self.assertRaises(UserError):
            wizard.action_create_co()
        self.assertFalse(co.line_ids)


@tagged('post_install', '-at_install')
class TestAnotacaoLevaAoDocumento(common.TransactionCase):
    """A anotação do chamado também leva à CO por link, e não por número
    escrito. Mesma decisão de 01/09/2026, e o mesmo motivo: quem lê o
    histórico quer chegar ao documento, não copiar o número dele."""

    def test_co_aberta_do_chamado_deixa_link_no_chamado(self):
        partner = self.env['res.partner'].create({
            'name': 'Livraria do Link', 'is_company': True,
            'allow_consignment': True,
        })
        self.env['consignment.agreement'].create({'partner_id': partner.id})
        self.env['product.product'].create({
            'name': 'Livro do Link', 'type': 'consu', 'is_storable': True,
            'list_price': 50.0, 'sale_ok': True,
        })
        team = self.env['liber.support.team'].create({
            'name': 'Comercial do Link', 'company_id': self.env.company.id,
            'alias_name': 'link-test',
        })
        ticket = self.env['liber.support.ticket'].create({
            'name': 'Pedido com link', 'team_id': team.id,
            'partner_id': partner.id,
        })
        wizard = self.env['liber.support.co.wizard']._open_for(ticket) \
            and self.env['liber.support.co.wizard'].search(
                [('ticket_id', '=', ticket.id)])
        wizard.source_text = '3 Livro do Link'
        wizard.action_parse()
        wizard.action_create_co()

        nota = ticket.message_ids.filtered(
            lambda m: 'data-oe-model="consignment.settlement"'
            in str(m.body))[:1]
        self.assertTrue(nota, "o chamado registrou a CO sem link")
        self.assertIn('data-oe-id="%s"' % ticket.settlement_id.id,
                      str(nota.body))


@tagged('post_install', '-at_install')
class TestColheitaCompartilhada(common.TransactionCase):
    """`_harvest` subiu do chamado para o assistente: as duas âncoras
    colhem a conversa pela MESMA função. Aqui só se prova que ela lê um
    registro qualquer com chatter — o efeito nas duas telas está nos
    testes de cada uma."""

    def test_harvest_le_email_e_ignora_nota_interna(self):
        partner = self.env['res.partner'].create({
            'name': 'Livraria da Colheita', 'allow_consignment': True,
        })
        self.env['consignment.agreement'].create({'partner_id': partner.id})
        co = self.env['consignment.settlement'].create({
            'partner_id': partner.id,
        })
        co.message_post(body=Markup('<p>3 Fim do SUS?</p>'),
                        message_type='email',
                        subtype_xmlid='mail.mt_comment')
        co.message_post(body=Markup('<p>90 Banguela</p>'),
                        message_type='comment',
                        subtype_xmlid='mail.mt_note')
        source, attachment = self.env['liber.support.co.wizard']._harvest(co)
        self.assertIn('Fim do SUS?', source)
        self.assertNotIn('Banguela', source,
                         "a nota interna entrou como se fosse o cliente")
        self.assertFalse(attachment)

    def test_parser_puro_da_nfe_da_livraria(self):
        self.assertEqual(
            co_parser.nfe_items(NFE_XML),
            [{'qty': 4, 'label': 'Fim do SUS?', 'isbn': '9788577151234'}])
