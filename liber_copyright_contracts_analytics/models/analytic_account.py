# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountAnalyticAccount(models.Model):
    """O menu do Copyright mostra os analíticos DELE, não o plano inteiro.

    Os analíticos de royalty nascem no plano que a empresa configura em Settings
    (``contract_analytic_group_id``). Antes, o menu do Copyright abria uma ação sem
    domínio nenhum -- ou seja, listava as 896 contas analíticas da casa inteira, o que
    engana: parece que tudo ali é direito autoral.
    """
    _inherit = 'account.analytic.account'

    is_copyright_analytic = fields.Boolean(
        string='Copyright', compute='_compute_is_copyright_analytic', store=True,
        help="A conta nasceu no plano analítico de contratos de direitos autorais "
             "(o plano que a empresa configura em Settings).")

    # Depende TAMBEM do ajuste da empresa: sem isso, trocar o plano de contratos
    # em Settings deixa a marca armazenada congelada no plano antigo -- e o menu
    # continua mostrando o conjunto errado, sem nenhum sinal de que envelheceu.
    # (Contas sem empresa nao sao recalculadas por essa dependencia; o cron/upgrade
    # as reavalia. Fica registrado que a cobertura ai e parcial.)
    @api.depends('plan_id', 'company_id', 'company_id.contract_analytic_group_id')
    def _compute_is_copyright_analytic(self):
        # o plano de contratos é por empresa; uma conta sem empresa vale se bater com
        # o plano de qualquer uma delas
        planos = {
            c.id: c._contract_analytic_plan().id
            for c in self.env['res.company'].sudo().search([])
        }
        todos = {p for p in planos.values() if p}
        for conta in self:
            if conta.company_id:
                conta.is_copyright_analytic = (
                    conta.plan_id.id == planos.get(conta.company_id.id))
            else:
                conta.is_copyright_analytic = conta.plan_id.id in todos
