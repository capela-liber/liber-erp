# -*- coding: utf-8 -*-
"""Definições: configurar sem que o segredo passeie pela tela."""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AmazonVendorCase


@tagged('post_install', '-at_install', 'amazon_vendor')
class TestAmazonSettings(AmazonVendorCase):

    def _settings(self, **overrides):
        """Abre a tela como o cliente abre: os valores vêm de get_values."""
        Settings = self.env['res.config.settings']
        values = Settings.default_get(list(Settings._fields))
        values.update(overrides)
        return Settings.create(values)

    # ------------------------------------------------------- o segredo fica

    def test_secrets_never_reach_the_form(self):
        """
        O core do Odoo devolve a senha guardada e só a pinta de bolinhas —
        quem abre o inspetor a lê. Aqui o campo chega vazio: o valor não sai
        do servidor.
        """
        settings = self._settings()
        self.assertFalse(settings.amazon_client_secret)
        self.assertFalse(settings.amazon_refresh_token)
        self.assertFalse(settings.amazon_client_id)
        # mas dá para saber que ela ESTÁ configurada, sem revelar nada
        self.assertTrue(settings.amazon_credentials_set)

    def test_saving_without_typing_keeps_the_credentials(self):
        """
        Campo em branco significa "mantém", nunca "apaga". Sem esta regra,
        abrir Definições e mudar qualquer outra coisa deixaria a conta sem
        credencial, e a importação da noite falharia sem ninguém ter tocado
        nela.
        """
        settings = self._settings(amazon_import_days_back=15)
        settings.set_values()

        account = self.account.sudo()
        self.assertEqual(account.refresh_token, 'Atzr|test')
        self.assertEqual(account.client_secret, 'amzn1.oa2-cs.v1.test')
        self.assertEqual(account.import_days_back, 15)

    def test_typing_a_new_secret_replaces_it(self):
        settings = self._settings(amazon_refresh_token='Atzr|novo')
        settings.set_values()
        self.assertEqual(self.account.sudo().refresh_token, 'Atzr|novo')

    def test_blank_string_does_not_erase(self):
        settings = self._settings(amazon_refresh_token='   ')
        settings.set_values()
        self.assertEqual(self.account.sudo().refresh_token, 'Atzr|test')

    # ------------------------------------------------------ o resto da tela

    def test_settings_show_the_account_of_the_current_company(self):
        settings = self._settings()
        self.assertEqual(settings.amazon_account_id, self.account)
        self.assertEqual(settings.amazon_account_name, self.account.name)
        self.assertEqual(settings.amazon_partner_id, self.partner_amazon)

    def test_settings_create_the_account_when_there_is_none(self):
        """Primeira configuração: nome e credencial numa tela só."""
        self.account.unlink()
        settings = self._settings(amazon_account_name='Nova conta',
                                  amazon_refresh_token='Atzr|primeiro',
                                  amazon_region='BR')
        settings.set_values()

        account = self.env['liber.amazon.account'].search(
            [('company_id', '=', self.company.id)])
        self.assertEqual(len(account), 1)
        self.assertEqual(account.name, 'Nova conta')
        self.assertEqual(account.sudo().refresh_token, 'Atzr|primeiro')

    def test_cron_toggle(self):
        cron = self.env.ref('liber_amazon_vendor.cron_liber_amazon_import')
        settings = self._settings(amazon_cron_active=False)
        settings.set_values()
        self.assertFalse(cron.active)

        settings = self._settings()
        self.assertFalse(settings.amazon_cron_active)
        settings = self._settings(amazon_cron_active=True)
        settings.set_values()
        self.assertTrue(cron.active)

    # ------------------------------------------------- o assistente vazio

    def test_wizard_explains_the_missing_account(self):
        """
        Combo vazio com um 'Criar...' solitário não conta o que houve. A
        causa quase sempre é empresa errada no seletor, e a mensagem diz isso.
        """
        self.account.unlink()
        with self.assertRaises(UserError) as caught:
            self.env['liber.amazon.import'].create({})
        self.assertIn('Settings', str(caught.exception))

    def test_wizard_points_at_the_company_selector(self):
        """
        Precisa de um usuário de verdade: em TransactionCase o `env.user` é o
        superusuário, e regra de registro não vale para ele. O teste rodando
        como superusuário provaria o contrário do que a operação vive.
        """
        other = self.env['res.company'].create({'name': 'Outra Casa'})
        self.account.company_id = other.id

        operator = self.env['res.users'].create({
            'name': 'So desta casa',
            'login': 'amazon_uma_empresa',
            'company_id': self.company.id,
            'company_ids': [(6, 0, [self.company.id])],
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('liber_amazon_vendor.group_liber_amazon_user').id,
            ])],
        })

        with self.assertRaises(UserError) as caught:
            self.env['liber.amazon.import'].with_user(operator).create({})
        self.assertIn('company', str(caught.exception).lower())
