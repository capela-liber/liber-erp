# -*- coding: utf-8 -*-
"""Testes da carta de correção (CC-e)."""

from unittest.mock import patch

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from .test_account_move_focus import preparar_documento_latam
from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.focus_client import FocusValidationError


class FakeFocusClient(object):
    def __init__(self, erro=None):
        self.erro = erro
        self.cartas = []

    def carta_correcao(self, ref, correcao):
        if self.erro:
            raise self.erro
        self.cartas.append((ref, correcao))
        return {'status': 'registrado', 'correcao': correcao}


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
