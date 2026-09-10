# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

# As faixas do relatório por idade, na ordem em que a tela as mostra, mais os
# dois baldes que ficam FORA da carteira. O rótulo é o que aparece na legenda
# do gráfico de evolução, então é curto de propósito.
FAIXAS = [
    ('current', 'Not due'),
    ('d30', '1-30'),
    ('d60', '31-60'),
    ('d90', '61-90'),
    ('d120', '91-120'),
    ('older', 'Older'),
    ('credit', 'Customer credits'),
    ('off_ledger', 'Wrong ledger'),
]
CARTEIRA = ('current', 'd30', 'd60', 'd90', 'd120', 'older')
CAMPO_DA_FAIXA = {
    'current': 'amount_current', 'd30': 'amount_30', 'd60': 'amount_60',
    'd90': 'amount_90', 'd120': 'amount_120', 'older': 'amount_older',
}

# O recorte da carteira, o MESMO que os pivôs do painel usam: lançado,
# conta viva, cliente de verdade (não é parceiro parado no razão errado) e
# saldo devedor. O crédito de cliente (residual negativo) e o parceiro fora
# do razão têm balde próprio, para a carteira não os absorver.
DOMINIO_BASE = [('move_state', '=', 'posted'),
                ('account_id.active', '=', True)]
DOMINIO_CARTEIRA = DOMINIO_BASE + [('partner_off_ledger', '=', False),
                                   ('amount_total', '>', 0)]
DOMINIO_CREDITO = DOMINIO_BASE + [('partner_off_ledger', '=', False),
                                  ('amount_total', '<', 0)]
DOMINIO_FORA_DO_RAZAO = DOMINIO_BASE + [('partner_off_ledger', '=', True)]


class LiberReceivablesSnapshot(models.Model):
    """A carteira de recebíveis fotografada, uma vez por mês, por empresa.

    O relatório por idade (`liber.aged.receivable`) é calculado contra a data
    de HOJE: ele diz quanto está vencido agora e não tem como dizer quanto
    estava vencido em março. Para o painel mostrar a evolução do vencido --
    se a cobrança está ganhando ou perdendo da venda -- alguém tem de guardar
    o número de cada mês. É isto.

    Uma linha por (dia, empresa, faixa). O gráfico do painel agrupa por mês e
    empilha as faixas; por isso só pode haver UMA foto por mês e por empresa,
    e a foto nova do mesmo mês substitui a anterior em vez de somar-se a ela.
    A foto é um número derivado, não um lançamento: apagar e refazer não
    perde nada que não se recalcule.
    """
    _name = 'liber.receivables.snapshot'
    _description = 'Receivables Snapshot'
    _order = 'date desc, company_id, bracket'
    _rec_name = 'date'

    date = fields.Date(string='Snapshot Date', required=True, index=True)
    company_id = fields.Many2one('res.company', string='Company',
                                 required=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    bracket = fields.Selection(FAIXAS, string='Bracket', required=True)
    amount = fields.Monetary(string='Amount', required=True)

    _unica_por_dia = models.Constraint(
        'UNIQUE(date, company_id, bracket)',
        'One snapshot per day, company and bracket.')

    # ------------------------------------------------------------------
    @api.model
    def _tirar_foto(self, dia=None):
        """Fotografa a carteira de toda empresa como ela está HOJE.

        `dia` é a data em que a foto fica guardada (o padrão é hoje). Não é
        a data que se fotografa: a view só sabe calcular o presente, e uma
        foto guardada "em março" com os números de hoje seria uma mentira
        com carimbo -- por isso um dia no futuro é recusado, e um dia no
        passado só serve para reposicionar a foto de hoje no mês que se
        quer (o caso de uso é o cron que rodou atrasado).
        """
        hoje = fields.Date.context_today(self)
        dia = fields.Date.to_date(dia) if dia else hoje
        if dia > hoje:
            raise UserError(self.env._(
                'A snapshot cannot be dated in the future (%(dia)s): the '
                'aging report only knows how the portfolio stands today.',
                dia=dia))
        Aged = self.env['liber.aged.receivable'].sudo()
        empresas = self.env['res.company'].sudo().search([])
        # A regra multi-empresa da view lê `company_ids` do contexto: para
        # fotografar todas, todas entram no contexto -- como o cron faz.
        Aged = Aged.with_context(allowed_company_ids=empresas.ids)
        valores = {}
        for company, *somas in Aged._read_group(
                DOMINIO_CARTEIRA, groupby=['company_id'],
                aggregates=[CAMPO_DA_FAIXA[f] + ':sum' for f in CARTEIRA]):
            for faixa, soma in zip(CARTEIRA, somas):
                valores[(company.id, faixa)] = soma or 0.0
        for dominio, faixa in ((DOMINIO_CREDITO, 'credit'),
                               (DOMINIO_FORA_DO_RAZAO, 'off_ledger')):
            for company, soma in Aged._read_group(
                    dominio, groupby=['company_id'],
                    aggregates=['amount_total:sum']):
                valores[(company.id, faixa)] = soma or 0.0

        Foto = self.sudo()
        primeiro = dia.replace(day=1)
        ultimo = fields.Date.end_of(dia, 'month')
        # Uma por mês: a foto nova do mês manda a anterior embora, de toda
        # empresa -- inclusive de uma empresa que hoje não tem saldo nenhum,
        # cujo zero também é informação.
        Foto.search([('date', '>=', primeiro), ('date', '<=', ultimo)]).unlink()
        linhas = [{
            'date': dia, 'company_id': company.id, 'bracket': faixa,
            'amount': valores.get((company.id, faixa), 0.0),
        } for company in empresas for faixa, _rotulo in FAIXAS]
        return Foto.create(linhas)

    @api.model
    def _cron_tirar_foto(self):
        self._tirar_foto()

    def action_tirar_foto(self):
        """O botão: a foto de hoje, agora, sem esperar o dia 1."""
        self._tirar_foto()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': self.env._("Today's snapshot of the receivables "
                                      "portfolio was taken."),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
