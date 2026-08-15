# -*- coding: utf-8 -*-
"""A conta de vendor: uma empresa, uma região, um par de credenciais."""

import logging
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..services.api import AmazonVendorApi, REGION_HOSTS

_logger = logging.getLogger(__name__)


class LiberAmazonAccount(models.Model):
    """
    Multiempresa desde o primeiro dia, e não por zelo abstrato.

    Cada vendor tem o seu próprio app e o seu próprio refresh token na Amazon:
    não existe credencial que atenda duas editoras. No dia em que este módulo
    servir outra casa -- que é o plano -- a conta já é um registro por empresa,
    e nada precisa ser desmontado. Guardar isso em `ir.config_parameter`, que
    é global, custaria a reescrita do módulo inteiro.
    """
    _name = 'liber.amazon.account'
    _description = 'Amazon Vendor Account'
    _inherit = ['mail.thread']
    _order = 'company_id, name'

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    region = fields.Selection(
        selection=[(code, code) for code in sorted(REGION_HOSTS)],
        default='BR', required=True, tracking=True,
        help="Which Amazon regional endpoint answers for this account. "
             "Brazil is served by the North America endpoint -- there is no "
             "Brazilian host.")

    # As credenciais. `groups` aqui não é decoração: sem isso qualquer usuário
    # que abra a ficha da conta lê o refresh token, e o refresh token é a conta
    # inteira -- com ele se obtém access token para tudo que o app autoriza.
    client_id = fields.Char(
        string='LWA Client ID', groups='base.group_system',
        help="Starts with amzn1.application-oa2-client.")
    client_secret = fields.Char(
        string='LWA Client Secret', groups='base.group_system')
    refresh_token = fields.Char(
        string='Refresh Token', groups='base.group_system',
        help="The long-lived token from the authorisation. Starts with Atzr|. "
             "Not the access token, which lasts one hour and is fetched "
             "automatically.")

    # A tela nunca mostra os campos de cima: mostra este espelho de escrita.
    # O compute devolve sempre vazio (o segredo gravado não volta ao
    # navegador -- password="True" só mascara o desenho, o valor viaja no
    # DOM) e o inverse grava apenas o que for digitado: em branco mantém.
    # Mesmo contrato da tela de Definições, que já nasceu assim.
    credentials_set = fields.Boolean(
        string='Credentials configured',
        compute='_compute_credentials_set',
        help="Whether this company already has a working refresh token "
             "stored.")
    client_id_input = fields.Char(
        string='LWA Client ID', groups='base.group_system',
        compute='_compute_secret_inputs', inverse='_inverse_client_id',
        help="Starts with amzn1.application-oa2-client.")
    client_secret_input = fields.Char(
        string='LWA Client Secret', groups='base.group_system',
        compute='_compute_secret_inputs', inverse='_inverse_client_secret')
    refresh_token_input = fields.Char(
        string='Refresh Token', groups='base.group_system',
        compute='_compute_secret_inputs', inverse='_inverse_refresh_token',
        help="The long-lived token from the authorisation. Starts with "
             "Atzr|. Not the access token, which lasts one hour and is "
             "fetched automatically.")

    @api.depends('refresh_token')
    def _compute_credentials_set(self):
        for account in self:
            account.credentials_set = bool(account.refresh_token)

    def _compute_secret_inputs(self):
        for account in self:
            account.client_id_input = False
            account.client_secret_input = False
            account.refresh_token_input = False

    def _inverse_client_id(self):
        for account in self:
            if account.client_id_input:
                account.client_id = account.client_id_input

    def _inverse_client_secret(self):
        for account in self:
            if account.client_secret_input:
                account.client_secret = account.client_secret_input

    def _inverse_refresh_token(self):
        for account in self:
            if account.refresh_token_input:
                account.refresh_token = account.refresh_token_input

    partner_id = fields.Many2one(
        'res.partner', string='Default Customer',
        help="Used only for orders that carry no buying unit code. Normally "
             "the customer comes from the unit map, because each Amazon "
             "warehouse is a separate legal establishment with its own tax "
             "registration.")
    unit_count = fields.Integer(compute='_compute_unit_count')

    import_days_back = fields.Integer(
        string='Re-read Window (days)', default=7,
        help="Every import also re-reads this many days before the last one. "
             "Amazon changes the state of an order after it was created -- a "
             "watermark that only moves forward would never see it.")

    last_import_date = fields.Datetime(readonly=True, copy=False)
    order_count = fields.Integer(compute='_compute_order_count')

    _name_company_uniq = models.Constraint(
        'unique(name, company_id)',
        'This company already has an Amazon account with that name.')

    @api.depends('name', 'region')
    def _compute_display_name(self):
        for record in self:
            record.display_name = '%s (%s)' % (record.name or '?', record.region)

    def _compute_unit_count(self):
        counts = dict(self.env['liber.amazon.unit']._read_group(
            [('account_id', 'in', self.ids)], ['account_id'], ['__count']))
        for record in self:
            record.unit_count = counts.get(record, 0)

    def _compute_order_count(self):
        counts = dict(self.env['liber.amazon.order']._read_group(
            [('account_id', 'in', self.ids)], ['account_id'], ['__count']))
        for record in self:
            record.order_count = counts.get(record, 0)

    # --------------------------------------------------------------- cliente

    def _api(self):
        """
        Monta o cliente. `sudo` porque as credenciais são de administrador e
        quem importa não precisa ser: o operador dispara a importação sem
        nunca poder ler o token.
        """
        self.ensure_one()
        account = self.sudo()
        missing = [label for label, value in (
            ('Client ID', account.client_id),
            ('Client Secret', account.client_secret),
            ('Refresh Token', account.refresh_token),
        ) if not value]
        if missing:
            raise UserError(_(
                "This Amazon account is missing: %s.", ", ".join(missing)))
        return AmazonVendorApi(
            client_id=account.client_id,
            client_secret=account.client_secret,
            refresh_token=account.refresh_token,
            region=account.region,
        )

    def action_test_connection(self):
        self.ensure_one()
        info = self._api().check()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Amazon answered"),
                'message': _(
                    "Region %(region)s via %(host)s. Nothing was imported.",
                    region=info['region'], host=info['host']),
                'sticky': False,
            },
        }

    # ------------------------------------------------------------ importação

    def _import_window(self):
        """
        De quando até quando ler.

        A janela recua `import_days_back` a partir da última importação em vez
        de continuar de onde parou. Marca d'água que só anda para frente
        funciona para dado imutável, e purchase order não é: a Amazon muda o
        estado depois de criado, e nesta conta 100% dos pedidos já nascem
        confirmados no portal. Sem o recuo, o estado no Odoo congelaria no
        instante da primeira leitura.
        """
        self.ensure_one()
        now = fields.Datetime.now()
        if self.last_import_date:
            start = self.last_import_date - timedelta(days=self.import_days_back or 0)
        else:
            start = now - timedelta(days=365)
        return start, now

    def action_import(self):
        """Lê a janela padrão e grava o espelho. Não cria cotação nenhuma."""
        summary = {'created': 0, 'updated': 0}
        for account in self:
            start, end = account._import_window()
            orders = account._api().purchase_orders(start, end)
            result = self.env['liber.amazon.order']._sync_from_amazon(
                account, orders)
            account.last_import_date = end
            summary['created'] += result['created']
            summary['updated'] += result['updated']

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Import finished"),
                'message': _(
                    "%(created)s new orders, %(updated)s updated. Nothing was "
                    "confirmed, here or at Amazon.",
                    created=summary['created'], updated=summary['updated']),
                'sticky': False,
            },
        }

    def action_map_units(self):
        """
        Cria uma linha de mapa para cada sigla que apareceu nos pedidos.

        O cliente vem em branco -- ou com um palpite, quando existe um
        parceiro cujo nome contém a sigla. O palpite é sugestão de tela, não
        regra do módulo: casar por nome funciona numa casa que batize os
        contatos de "Amazon GRU8" e em nenhuma outra, e uma convenção de
        cadastro de uma editora não pode virar comportamento embutido. Por
        isso ele só acontece quando alguém aperta este botão, e fica visível
        para conferência antes de qualquer nota ser emitida.
        """
        self.ensure_one()
        Unit = self.env['liber.amazon.unit']

        siglas = {
            pedido.buying_party
            for pedido in self.env['liber.amazon.order'].search(
                [('account_id', '=', self.id), ('buying_party', '!=', False)])
        }
        ja_mapeadas = set(Unit.search(
            [('account_id', '=', self.id)]).mapped('code'))
        novas = sorted(siglas - ja_mapeadas)

        criadas = Unit
        for sigla in novas:
            palpite = self.env['res.partner'].search(
                [('name', 'ilike', sigla)], limit=2)
            criadas |= Unit.create({
                'account_id': self.id,
                'code': sigla,
                # Só aceita o palpite quando ele é único: dois candidatos são
                # uma pergunta, não uma resposta.
                'partner_id': palpite.id if len(palpite) == 1 else False,
            })

        return {
            'type': 'ir.actions.act_window',
            'name': _("Amazon Units"),
            'res_model': 'liber.amazon.unit',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.id)],
            'context': {'default_account_id': self.id},
        }

    def action_view_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Amazon Orders"),
            'res_model': 'liber.amazon.order',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.id)],
            'context': {'default_account_id': self.id},
        }

    @api.model
    def _cron_import(self):
        """
        A rotina diária.

        Uma conta que falha não derruba as outras: a Amazon recusar o token de
        uma editora não é motivo para a importação das demais não acontecer. O
        erro vai para o log e a conta seguinte é tentada.
        """
        for account in self.search([]):
            try:
                account.action_import()
                self.env.cr.commit()
            except Exception:  # noqa: BLE001 - uma conta ruim não para as outras
                self.env.cr.rollback()
                _logger.exception(
                    "Amazon Vendor: import failed for account %s", account.id)
