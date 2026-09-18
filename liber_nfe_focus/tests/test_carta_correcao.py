# -*- coding: utf-8 -*-
"""Testes da carta de correção (CC-e)."""

from unittest.mock import patch

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from .test_account_move_focus import preparar_documento_latam
from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.focus_client import FocusError, FocusValidationError


PDF_CARTA = b'%PDF-1.4 carta de correcao'


class FakeFocusClient(object):
    """Cliente falso. Com `com_pdf`, responde como a Focus de verdade: o
    caminho do PDF da carta e o número dela vêm na resposta do envio."""

    def __init__(self, erro=None, com_pdf=False, pdf_falha=False):
        self.erro = erro
        self.com_pdf = com_pdf
        self.pdf_falha = pdf_falha
        self.cartas = []
        self.baixados = []

    def carta_correcao(self, ref, correcao):
        if self.erro:
            raise self.erro
        self.cartas.append((ref, correcao))
        resposta = {'status': 'autorizado', 'correcao': correcao}
        if self.com_pdf:
            n = len(self.cartas)
            resposta.update({
                'numero_carta_correcao': n,
                'caminho_xml_carta_correcao': '/arquivos/x/cce-%d.xml' % n,
                'caminho_pdf_carta_correcao': '/arquivos/x/cce-%d.pdf' % n,
            })
        return resposta

    def baixar(self, caminho):
        self.baixados.append(caminho)
        if self.pdf_falha:
            raise FocusError('Falha ao baixar %s (HTTP 500).' % caminho)
        if caminho.endswith('.pdf'):
            return PDF_CARTA + caminho.encode()
        n = caminho.rsplit('-', 1)[-1].split('.')[0]
        return ('<procEventoNFe><evento><infEvento><tpEvento>110110</tpEvento>'
                '<nSeqEvento>%s</nSeqEvento></infEvento></evento>'
                '</procEventoNFe>' % n).encode()


@tagged('post_install', '-at_install', 'focus_nfe')
class TestCartaCorrecao(AccountTestInvoicingCommon):

    chart_template = 'generic_coa'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'focus_ambiente': 'homologacao',
            'focus_token_homologacao': 'tok-teste',
        })
        cls.cliente = cls.env['res.partner'].create({'name': 'Livraria'})

    def _nota_autorizada(self):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.cliente.id,
            'invoice_date': '2026-07-30',
            'invoice_line_ids': [(0, 0, {
                'name': 'Livro', 'quantity': 1, 'price_unit': 10,
                'tax_ids': [(5, 0, 0)]})],
        })
        preparar_documento_latam(move)
        move.action_post()
        move.write({'focus_ref': 'TESTE-1', 'focus_ambiente': 'homologacao'})
        move._focus_aplicar_resposta(
            {'status': 'autorizado', 'chave_nfe': '8' * 44})
        return move

    def _enviar(self, move, texto, falso=None):
        falso = falso or FakeFocusClient()
        wizard = self.env['nfe.focus.correcao.wizard'].with_context(
            default_move_id=move.id).create({'correcao': texto})
        with patch.object(type(move), '_focus_client_da_nota', return_value=falso):
            wizard.action_enviar()
        return falso

    # -- caminho feliz -------------------------------------------------
    def test_carta_vai_para_a_sefaz_e_fica_no_historico(self):
        move = self._nota_autorizada()

        falso = self._enviar(move, 'Onde se le Rua A, leia-se Rua B')

        self.assertEqual(falso.cartas[0][0], 'TESTE-1')
        self.assertIn('leia-se Rua B', falso.cartas[0][1])
        self.assertIn('leia-se Rua B', move.focus_correcoes)

    def test_segunda_carta_se_acumula_no_historico(self):
        """No histórico elas se somam, para haver rastro. Na SEFAZ a última
        substitui a anterior -- por isso o assistente mostra as duas coisas."""
        move = self._nota_autorizada()

        self._enviar(move, 'Primeira correcao do endereco')
        self._enviar(move, 'Segunda correcao, agora do transportador')

        self.assertIn('Primeira correcao', move.focus_correcoes)
        self.assertIn('Segunda correcao', move.focus_correcoes)

    def test_assistente_ja_vem_com_a_ultima_carta(self):
        """Campo vazio convidaria a escrever só o acréscimo — e, como a nova
        substitui a anterior, isso revogaria a correção que já valia."""
        move = self._nota_autorizada()
        self._enviar(move, 'Onde se le Rua A, leia-se Rua B')

        wizard = self.env['nfe.focus.correcao.wizard'].with_context(
            default_move_id=move.id).create({})

        self.assertIn('leia-se Rua B', wizard.correcao)
        self.assertIn('leia-se Rua B', wizard.historico)

    # -- o PDF da carta ------------------------------------------------
    def _cartas_da(self, move):
        return move._focus_anexos_de_carta()

    def test_pdf_da_carta_fica_na_fatura_com_a_mensagem(self):
        """A Focus gera PDF para a carta (e só para ela). O comercial olha a
        fatura: é lá que o PDF tem de estar, ao lado do DANFE, e carregado
        pela mensagem que anuncia a carta."""
        move = self._nota_autorizada()
        antes = len(move.message_ids)

        falso = self._enviar(move, 'Onde se le Rua A, leia-se Rua B',
                             FakeFocusClient(com_pdf=True))

        self.assertIn('/arquivos/x/cce-1.pdf', falso.baixados)
        cartas = self._cartas_da(move)
        self.assertEqual(cartas.mapped('name'),
                         ['TESTE-1-carta-correcao-1.pdf'])
        self.assertEqual(cartas.mimetype, 'application/pdf')
        self.assertTrue(cartas.raw.startswith(PDF_CARTA))
        novas = move.message_ids[:len(move.message_ids) - antes]
        self.assertTrue(any(cartas <= m.attachment_ids for m in novas),
                        "a mensagem da carta tem de carregar o PDF")
        self.assertTrue(any('nº 1' in (m.body or '') for m in novas))

    def test_segunda_carta_ganha_o_seu_pdf_e_a_primeira_fica(self):
        """Na SEFAZ a última substitui a anterior; no histórico as duas
        ficam, cada uma com o seu número."""
        move = self._nota_autorizada()
        falso = FakeFocusClient(com_pdf=True)

        self._enviar(move, 'Primeira correcao do endereco', falso)
        self._enviar(move, 'Segunda correcao, agora do transportador', falso)

        self.assertEqual(self._cartas_da(move).mapped('name'), [
            'TESTE-1-carta-correcao-1.pdf', 'TESTE-1-carta-correcao-2.pdf'])

    def test_reconsulta_nao_duplica_o_pdf_nem_a_mensagem(self):
        """O cron consulta a nota todo dia; a resposta da consulta traz o
        mesmo caminho da carta. Uma carta, um anexo, uma mensagem."""
        move = self._nota_autorizada()
        falso = FakeFocusClient(com_pdf=True)
        self._enviar(move, 'Onde se le Rua A, leia-se Rua B', falso)
        mensagens = len(move.message_ids)
        resposta = {
            'status': 'autorizado', 'chave_nfe': '8' * 44,
            'numero_carta_correcao': 1,
            'caminho_xml_carta_correcao': '/arquivos/x/cce-1.xml',
            'caminho_pdf_carta_correcao': '/arquivos/x/cce-1.pdf',
        }

        with patch.object(type(move), '_focus_client_da_nota', return_value=falso):
            move._focus_guardar_documentos(resposta)
            move._focus_guardar_documentos(resposta)

        self.assertEqual(len(self._cartas_da(move)), 1)
        self.assertEqual(len(move.message_ids), mensagens,
                         "anexo que já existia não gera aviso novo")

    def test_carta_emitida_fora_chega_pela_consulta(self):
        """Carta feita no painel da Focus, sem passar pelo assistente: a
        consulta é a rede. Sem número na resposta, o `nSeqEvento` do XML
        numera o anexo -- e aí a mensagem nasce aqui."""
        move = self._nota_autorizada()
        falso = FakeFocusClient(com_pdf=True)
        antes = len(move.message_ids)
        resposta = {
            'status': 'autorizado', 'chave_nfe': '8' * 44,
            'caminho_xml_carta_correcao': '/arquivos/x/cce-3.xml',
            'caminho_pdf_carta_correcao': '/arquivos/x/cce-3.pdf',
        }

        with patch.object(type(move), '_focus_client_da_nota', return_value=falso):
            move._focus_guardar_documentos(resposta)

        self.assertEqual(self._cartas_da(move).mapped('name'),
                         ['TESTE-1-carta-correcao-3.pdf'])
        self.assertEqual(falso.baixados.count('/arquivos/x/cce-3.xml'), 1,
                         "o XML da carta desce uma vez: PDF e painel dividem")
        novas = move.message_ids[:len(move.message_ids) - antes]
        self.assertTrue(any('nº 3' in (m.body or '') for m in novas))

    def test_pdf_que_nao_baixou_nao_derruba_a_carta(self):
        """A carta já vale na SEFAZ quando o download falha: o texto entra
        no histórico, o PDF fica para a próxima consulta."""
        move = self._nota_autorizada()

        self._enviar(move, 'Onde se le Rua A, leia-se Rua B',
                     FakeFocusClient(com_pdf=True, pdf_falha=True))

        self.assertIn('leia-se Rua B', move.focus_correcoes)
        self.assertFalse(self._cartas_da(move))

    # -- casos de erro -------------------------------------------------
    def test_nota_nao_autorizada_nao_tem_o_que_corrigir(self):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.cliente.id,
            'invoice_date': '2026-07-30',
            'invoice_line_ids': [(0, 0, {
                'name': 'Livro', 'quantity': 1, 'price_unit': 10,
                'tax_ids': [(5, 0, 0)]})],
        })
        preparar_documento_latam(move)
        move.action_post()

        with self.assertRaises(UserError):
            move.action_focus_carta_correcao()

    def test_recusa_da_sefaz_vira_mensagem(self):
        move = self._nota_autorizada()
        falso = FakeFocusClient(erro=FocusValidationError(
            'Rejeicao: correcao nao pode alterar valores'))

        with self.assertRaises(UserError) as ctx:
            self._enviar(move, 'Trocar o valor total para 20 reais', falso)

        self.assertIn('nao pode alterar valores', str(ctx.exception))

    def test_texto_curto_e_barrado_pelo_cliente(self):
        """A SEFAZ exige de 15 a 1000 caracteres."""
        from ..models.focus_client import FocusClient
        client = FocusClient('tok', ambiente='homologacao')

        with self.assertRaises(FocusValidationError):
            client.carta_correcao('TESTE-1', 'erro')

    def test_limite_de_vinte_cartas(self):
        move = self._nota_autorizada()
        blocos = ['[2026-07-30 10:00:00] correcao numero %d' % i
                  for i in range(20)]
        move.write({'focus_correcoes': '\n\n'.join(blocos)})

        with self.assertRaises(UserError) as ctx:
            self._enviar(move, 'Esta seria a vigesima primeira carta')

        self.assertIn('limite', str(ctx.exception))
