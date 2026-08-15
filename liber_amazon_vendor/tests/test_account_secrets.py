# -*- coding: utf-8 -*-
"""O segredo gravado não volta ao navegador — nem na tela da conta.

A tela de Definições nasceu com este contrato; o formulário da conta o
ganhou depois: os campos que a view mostra são espelhos de escrita
(client_id_input e irmãos). O compute devolve sempre vazio, o inverse grava
só o que for digitado, e em branco mantém o que já está salvo.
"""
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import AmazonVendorCase


@tagged('post_install', '-at_install', 'amazon_vendor')
class TestAccountSecrets(AmazonVendorCase):

    def test_espelho_chega_sempre_vazio(self):
        """Os três segredos estão gravados; os espelhos leem vazio."""
        self.assertTrue(self.account.client_id)
        self.assertTrue(self.account.client_secret)
        self.assertTrue(self.account.refresh_token)
        self.assertFalse(self.account.client_id_input)
        self.assertFalse(self.account.client_secret_input)
        self.assertFalse(self.account.refresh_token_input)
        self.assertTrue(self.account.credentials_set)

    def test_digitar_troca(self):
        self.account.write({'refresh_token_input': 'Atzr|novo'})
        self.assertEqual(self.account.refresh_token, 'Atzr|novo')
        self.account.write({'client_id_input': 'amzn1.application-oa2-client.b',
                            'client_secret_input': 'amzn1.oa2-cs.v1.b'})
        self.assertEqual(self.account.client_id,
                         'amzn1.application-oa2-client.b')
        self.assertEqual(self.account.client_secret, 'amzn1.oa2-cs.v1.b')

    def test_em_branco_mantem(self):
        """Edge case: salvar o formulário com os espelhos vazios (que é como
        eles sempre chegam) não pode apagar o que está gravado."""
        antes = self.account.refresh_token
        self.account.write({
            'client_id_input': False,
            'client_secret_input': False,
            'refresh_token_input': False,
        })
        self.assertEqual(self.account.refresh_token, antes)
        self.assertTrue(self.account.client_id)
        self.assertTrue(self.account.credentials_set)

    def test_conta_nova_sem_credencial(self):
        conta = self.env['liber.amazon.account'].create({
            'name': 'Vendor Sem Chave', 'region': 'BR',
            'company_id': self.company.id})
        self.assertFalse(conta.credentials_set)
        conta.write({'refresh_token_input': 'Atzr|primeiro'})
        self.assertTrue(conta.credentials_set)

    def test_espelho_tambem_e_de_sistema(self):
        """Caso de erro: quem não é administrador de sistema não lê nem o
        espelho — o groups= do campo real vale igual para o input."""
        user = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Sem Sistema', 'login': 'sem.sistema@test',
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
            })
        with self.assertRaises(AccessError):
            self.account.with_user(user).read(['client_id_input'])
