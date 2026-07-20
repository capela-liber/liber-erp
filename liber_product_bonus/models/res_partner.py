# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from .bonus_rating import SCORE_HELP


# Who the recipient IS -- distinct from the investment (which budget pays). A
# journalist is a partner type; Marketing is an investment. Single value on
# purpose: it is a report dimension, and "22% of marketing went to influencers"
# only reads cleanly if each person is one type.
PARTNER_TYPES = [
    ('author', 'Author'),
    ('journalist', 'Journalist'),
    ('influencer', 'Influencer'),
    ('bookshop', 'Bookshop'),
    ('other', 'Other'),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_bonus_recipient = fields.Boolean(string="Bonus recipient")
    bonus_partner_type = fields.Selection(
        PARTNER_TYPES, string="Partner type",
        help="Who they are (author, journalist, influencer, bookshop) -- not "
             "which budget pays for the book. That is the investment.")
    # Uma linha, não um texto: é feita para ser COLUNA na seleção do BO
    # ("Crítica literária da Folha", "Booktuber, 80 mil seguidores"). O que
    # couber numa linha decide um envio; o que precisar de parágrafo vai para
    # as Notas do contato, como sempre.
    bonus_bio = fields.Char(
        string="Who they are",
        help="One line saying who this person is in the book world -- shown "
             "next to the name wherever bonus copies are decided.")

    bonus_ids = fields.One2many('product.bonus', 'partner_id')
    # Armazenado para poder ORDENAR por ele na tela de contatos por lista:
    # coluna de campo calculado não vira ORDER BY.
    bonus_count = fields.Integer(compute='_compute_bonus_stats', store=True)

    # Em quantas listas esta pessoa está.
    #
    # Armazenado porque a pergunta que se faz com ele é sempre ordenada --
    # "quem está em lista demais?" -- e ordenar exige coluna. É também o
    # detector de lista redundante: quando as mesmas trinta pessoas aparecem em
    # oito listas, as oito são a mesma lista com nomes diferentes.
    bonus_list_member_ids = fields.One2many(
        'product.bonus.list.member', 'partner_id', string="Participações")
    bonus_list_count = fields.Integer(
        compute='_compute_bonus_list_count', store=True, string="Listas")
    bonus_list_names = fields.Char(
        compute='_compute_bonus_list_count', string="Em quais listas")
    bonus_last_date = fields.Date(compute='_compute_bonus_stats')
    bonus_lifetime_cost = fields.Float(compute='_compute_bonus_stats')

    # Raw rate, never a score.
    #
    # The obvious temptation is great=3, good=2, weak=1 -> "Influencer score:
    # 68", with a ranking. It is a guess with decimal places: it launders
    # judgement into a number nobody can argue with, it hides the n (one book
    # and one "nailed it" scores 100 and proves nothing), and the day somebody
    # is measured on the list's average score, the hard names -- the ones that
    # matter -- quietly disappear from the list.
    bonus_outcome_ok = fields.Integer(compute='_compute_bonus_stats')
    bonus_outcome_judged = fields.Integer(compute='_compute_bonus_stats')
    bonus_outcome_rate = fields.Char(compute='_compute_bonus_stats', string="Avaliação")

    # Nível e direção. A fração continua existindo (é o dado cru, auditável);
    # a nota é o que se lê na hora de escolher. Ver bonus_rating.py para o
    # porquê de cada mecanismo -- e para o que ela deliberadamente não faz.
    bonus_rating = fields.Float(
        compute='_compute_bonus_rating', store=True, string="Score",
        help="Média dos resultados ponderada por recência, encolhida para a "
             "média da casa enquanto há pouco histórico. Zero enquanto em teste.")
    bonus_rating_label = fields.Char(
        compute='_compute_bonus_rating', string="Score", help=SCORE_HELP)
    # A versão marcada, para a tela. sanitize=False porque a marcação é NOSSA,
    # gerada aqui -- nada aqui vem de entrada de usuário.
    bonus_rating_html = fields.Html(
        compute='_compute_bonus_rating', string="Score", sanitize=False,
        help=SCORE_HELP)
    bonus_rating_trend = fields.Char(
        compute='_compute_bonus_rating', string="Direção")
    # Armazenado porque relatório em pivot/graph só agrupa por campo com
    # coluna: sem isto, "quanto gastamos com quem esfriou" não é perguntável.
    bonus_rating_band = fields.Selection([
        ('new', "Novo"),
        ('testing', "Em teste"),
        ('cold', "Sem retorno"),
        ('fading', "Esfriando"),
        ('steady', "Constante"),
        ('warm', "Rendendo"),
    ], compute='_compute_bonus_rating', store=True, string="Situação")

    @api.depends('bonus_ids.outcome', 'bonus_ids.state', 'bonus_ids.date')
    def _compute_bonus_rating(self):
        Rating = self.env['bonus.rating.mixin']
        points, test_size, _half = Rating._rating_settings()
        for rec in self:
            score, label, trend, n = Rating._rating_for(rec.bonus_ids)
            rec.bonus_rating = score or 0.0
            rec.bonus_rating_label = label
            rec.bonus_rating_trend = trend
            if not n:
                rec.bonus_rating_band = 'new'
            elif score is None:
                rec.bonus_rating_band = 'testing'
            elif score <= points.get('weak', 5.0) / 2.0:
                # Abaixo de meia meia-boca: 22 livros e nada de volta mora aqui.
                rec.bonus_rating_band = 'cold'
            elif trend == '↓':
                rec.bonus_rating_band = 'fading'
            elif trend == '↑':
                rec.bonus_rating_band = 'warm'
            else:
                rec.bonus_rating_band = 'steady'
            rec.bonus_rating_html = Rating._rating_html(
                label, rec.bonus_rating_band, n, test_size)

    # There is no "do not send any more" flag here, on purpose. Deciding a
    # journalist is off the list forever is an editorial/relationship call, not
    # bonus bookkeeping -- it does not belong in this module. The history is
    # here to inform that decision (22 books, zero return); where the decision
    # gets recorded, if anywhere, is somewhere else.

    @api.depends('bonus_list_member_ids.active', 'bonus_list_member_ids.list_id')
    def _compute_bonus_list_count(self):
        # O one2many já vem só com participação ativa (active_test), e é isso
        # que se quer: quem saiu de uma lista não está nela. A lista arquivada,
        # porém, ainda contaria -- daí o filtro explícito.
        for partner in self:
            listas = partner.bonus_list_member_ids.list_id.filtered('active')
            partner.bonus_list_count = len(listas)
            partner.bonus_list_names = ", ".join(sorted(listas.mapped('name')))

    @api.depends('bonus_ids.state', 'bonus_ids.outcome', 'bonus_ids.total_cost')
    def _compute_bonus_stats(self):
        for rec in self:
            live = rec.bonus_ids.filtered(lambda b: b.state != 'cancelled')
            rec.bonus_count = len(live)
            rec.bonus_last_date = max(live.mapped('date'), default=False)
            rec.bonus_lifetime_cost = sum(live.mapped('total_cost'))
            judged = live.filtered(lambda b: b.outcome)
            ok = judged.filtered(lambda b: b.outcome in ('good', 'great'))
            rec.bonus_outcome_ok = len(ok)
            rec.bonus_outcome_judged = len(judged)
            # "—", never "0 of 0". If no history looked bad, nobody new would
            # ever get a first book -- and without a first book there is never
            # any history. The list would freeze on the same 30 names from 2019
            # and the house would stop discovering people. It is an invitation,
            # not a demerit.
            rec.bonus_outcome_rate = (
                "%d de %d" % (len(ok), len(judged)) if judged else "—")

    @api.model
    def _cron_recompute_bonus_rating(self):
        """O score armazenado precisa ser recalculado de tempos em tempos.

        Ele pondera por recência: uma avaliação de 13 meses atrás vale menos
        hoje do que valia ontem, e a média da casa muda quando OUTRAS pessoas
        são avaliadas. Nada disso mexe nos registros deste contato, então um
        campo armazenado envelheceria calado -- alguém que esfriou continuaria
        aparecendo quente até receber outro livro, que é justamente o que não
        vai acontecer.

        Só quem tem histórico entra: a base tem dezenas de milhares de
        contatos e a esmagadora maioria nunca recebeu nada.
        """
        partners = self.search([('bonus_ids', '!=', False)])
        self.env.add_to_compute(self._fields['bonus_rating'], partners)
        self.env.add_to_compute(self._fields['bonus_rating_band'], partners)
        self.env.flush_all()
        return True

    def action_view_bonuses(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _("Bonificações — %s", self.display_name),
            'res_model': 'product.bonus',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
        bonuses = self.env['product.bonus'].search([('partner_id', '=', self.id)])
        if len(bonuses) == 1:
            action.update(view_mode='form', res_id=bonuses.id)
        else:
            action['view_mode'] = 'list,form'
        return action
