# -*- coding: utf-8 -*-
"""
A conta da Amazon também em Definições, e não só dentro do app.

Quem chega para configurar procura em Definições — é onde mora tudo o mais.
Obrigar a pessoa a descobrir que este módulo esconde a configuração num menu
próprio é pegadinha, ainda que o menu exista.

Sobre segredo, aqui o cuidado é maior que o do core do Odoo. O core devolve a
senha guardada para o navegador e só a pinta de bolinhas — quem abrir o
inspetor a lê. Neste formulário o `client_id`, o `client_secret` e o
`refresh_token` **nunca saem do servidor**: chegam vazios, e em branco quer
dizer "mantém o que já está lá". Só se a pessoa digitar é que se grava. O
preço é não poder conferir o valor atual pela tela; o ganho é que ele não
trafega nem fica no DOM.

Os campos são simples e a leitura/gravação passa por `get_values`/`set_values`
— o padrão do `res.config.settings`. Tentar fazer isso com campos calculados
não funciona: qualquer recompute descarta o que a pessoa digitou.
"""

from odoo import api, fields, models, _

from ..services.api import REGION_HOSTS


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    amazon_account_id = fields.Many2one(
        'liber.amazon.account', string='Amazon Account', readonly=True)
    amazon_account_name = fields.Char(string='Account Name')
    amazon_region = fields.Selection(
        selection=[(code, code) for code in sorted(REGION_HOSTS)],
        string='Amazon Region', default='BR')
    amazon_partner_id = fields.Many2one(
        'res.partner', string='Amazon as Customer')
    amazon_import_days_back = fields.Integer(
        string='Re-read Window (days)', default=7)

    # Status legível por qualquer administrador, sem revelar nada.
    amazon_credentials_set = fields.Boolean(
        string='Credentials Configured', readonly=True)
    amazon_last_import_date = fields.Datetime(string='Last Import', readonly=True)

    # Os segredos. `groups` impede que quem não é administrador do sistema os
    # escreva; `get_values` nunca os devolve.
    amazon_client_id = fields.Char(
        string='LWA Client ID', groups='base.group_system')
    amazon_client_secret = fields.Char(
        string='LWA Client Secret', groups='base.group_system')
    amazon_refresh_token = fields.Char(
        string='Refresh Token', groups='base.group_system')

    amazon_cron_active = fields.Boolean(string='Daily Import')

    def _amazon_account(self):
        """A conta da empresa que o seletor de Definições está apontando."""
        return self.env['liber.amazon.account'].sudo().search(
            [('company_id', '=', self.env.company.id)], limit=1)

    def _amazon_cron(self):
        return self.env.ref('liber_amazon_vendor.cron_liber_amazon_import',
                            raise_if_not_found=False)

    @api.model
    def get_values(self):
        values = super().get_values()
        account = self._amazon_account()
        cron = self._amazon_cron()
        values.update({
            'amazon_account_id': account.id or False,
            'amazon_account_name': account.name or '',
            'amazon_region': account.region or 'BR',
            'amazon_partner_id': account.partner_id.id or False,
            'amazon_import_days_back': account.import_days_back or 7,
            'amazon_last_import_date': account.last_import_date or False,
            'amazon_credentials_set': bool(account and account.refresh_token),
            'amazon_cron_active': bool(cron and cron.active),
            # Deliberadamente ausentes: 'amazon_client_id',
            # 'amazon_client_secret', 'amazon_refresh_token'. O que não é
            # enviado não pode vazar.
        })
        return values

    def set_values(self):
        super().set_values()

        cron = self._amazon_cron()
        if cron and cron.active != self.amazon_cron_active:
            cron.sudo().active = self.amazon_cron_active

        account = self._amazon_account()
        values = {
            'region': self.amazon_region or 'BR',
            'import_days_back': self.amazon_import_days_back or 7,
            'partner_id': self.amazon_partner_id.id or False,
        }

        # Campo de segredo em branco = não mexer. Sem esta regra, abrir
        # Definições e salvar qualquer outra coisa apagaria as credenciais, e a
        # importação da noite falharia sem ninguém ter tocado nelas.
        if self.env.user.has_group('base.group_system'):
            for field_name, target in (('amazon_client_id', 'client_id'),
                                       ('amazon_client_secret', 'client_secret'),
                                       ('amazon_refresh_token', 'refresh_token')):
                typed = (self[field_name] or '').strip()
                if typed:
                    values[target] = typed

        if account:
            if self.amazon_account_name:
                values['name'] = self.amazon_account_name
            account.write(values)
        elif self.amazon_account_name or values.get('refresh_token'):
            # Criar a conta daqui é o caminho mais curto para quem configura
            # pela primeira vez: nome e credencial numa tela só.
            values.update({
                'name': self.amazon_account_name or _("Amazon Vendor"),
                'company_id': self.env.company.id,
            })
            self.env['liber.amazon.account'].sudo().create(values)

    def action_open_amazon_accounts(self):
        """Para quem tem mais de uma empresa: a lista inteira, não só esta."""
        return self.env.ref(
            'liber_amazon_vendor.action_liber_amazon_account').read()[0]
