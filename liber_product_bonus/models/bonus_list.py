# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from .bonus_rating import SCORE_HELP


class ProductBonusListTag(models.Model):
    """Because "centenas de listas VIP" is a navigation problem before it is
    anything else. A name alone does not survive 300 rows."""
    _name = 'product.bonus.list.tag'
    _description = 'VIP List Tag'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer()

    _name_uniq = models.Constraint('unique(name)', 'Tag already exists.')


class ProductBonusList(models.Model):
    """A VIP list is not a tag on contacts.

    It has a history: who built it, what it spent, who answers for it. It is a
    shipping machine with an owner and a budget -- and it is as much the
    *output* of a good triage as it is the input.
    """
    _name = 'product.bonus.list'
    _description = 'VIP List'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(
        default=True,
        help="Archive instead of deleting: a list that shipped books is "
             "history, and history does not get thrown away because it stopped "
             "being useful.")
    tag_ids = fields.Many2many('product.bonus.list.tag', string="Tags")

    # Provenance: where this list came from. "Montada a partir de Imprensa SP +
    # Influencers de poesia" is the kind of thing nobody remembers in a year,
    # and it is exactly what makes a list trustworthy or suspect.
    # context active_test=False porque arquivar as originárias é o caminho
    # NORMAL depois de combinar -- e sem isto o campo ficaria vazio justamente
    # aí, que é quando a procedência é a única memória de onde a gente veio.
    source_list_ids = fields.Many2many(
        'product.bonus.list', 'bonus_list_source_rel', 'child_id', 'parent_id',
        string="Combined from", readonly=True,
        context={'active_test': False})
    combine_mode = fields.Selection([
        ('union', 'Union'),
        ('intersection', 'Intersection'),
        ('difference', 'Difference'),
    ], readonly=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda s: s.env.company)

    user_id = fields.Many2one(
        'res.users', string="Owner", required=True, tracking=True,
        default=lambda s: s.env.user,
        help="Approves the bonus copies from this list.")
    built_by_id = fields.Many2one(
        'res.users', string="Built by", readonly=True,
        default=lambda s: s.env.user)
    built_on = fields.Date(readonly=True, default=fields.Date.context_today)
    # Não é "montada em": é a última vez que este título SAIU. Numa lista
    # importada das SOBs do Odoo 15, "montada em" é o dia do import -- a mesma
    # data para as 132, e portanto informação nenhuma. O que diz se a lista
    # ainda está viva é o último envio, e por isso ele ordena: a pergunta
    # "quais esfriaram" é um clique no cabeçalho.
    last_shipment_on = fields.Date(
        string="Last shipment", tracking=True,
        help="When this list last shipped a book. Imported lists carry the "
             "date of the last shipment found in the history.")
    note = fields.Text()

    quota_qty = fields.Float(
        string="Donation target",
        help="The ceiling the bonus copies of this list have to fit in.")

    bonus_ids = fields.One2many(
        'product.bonus', 'list_id', string="Bonificações")
    member_ids = fields.One2many('product.bonus.list.member', 'list_id')
    # Armazenados para poder ORDENAR: com 132 listas importadas, "quais são as
    # maiores" e "quais nunca renderam nada" são perguntas de clique no
    # cabeçalho, e coluna calculada não vira ORDER BY.
    member_count = fields.Integer(compute='_compute_stats', store=True)
    bonus_count = fields.Integer(compute='_compute_stats', store=True)
    spent = fields.Float(compute='_compute_stats', store=True, string="Spent")
    outcome_rate = fields.Char(
        compute='_compute_stats', string="Avaliação",
        help="Raw rate, never a score. Tells which list is worth it and which "
             "one became junk mail.")
    # A fração ("19 de 58") não pode ser ordenada como texto: "19 de 58" viria
    # antes de "5 de 7", que é o oposto do que a coluna parece prometer. Este
    # aqui é o número por trás dela, ordenável -- fora da tela por padrão,
    # porque a fração é mais honesta de ler (ela mostra o tamanho da amostra).
    outcome_pct = fields.Float(
        compute='_compute_stats', store=True, string="Aval. %",
        aggregator=False,
        help="Proporção de avaliações positivas. Serve para ordenar; a fração "
             "ao lado é o que se lê, porque mostra de quantas.")
    currency_id = fields.Many2one(related='company_id.currency_id')

    # As dependências têm que atravessar para product.bonus: armazenado sem
    # isto congela no valor do dia em que a lista foi criada.
    @api.depends('member_ids.active', 'bonus_ids.state', 'bonus_ids.outcome',
                 'bonus_ids.total_cost')
    def _compute_stats(self):
        for rec in self:
            rec.member_count = len(rec.member_ids.filtered('active'))
            bonuses = rec.bonus_ids
            rec.bonus_count = len(bonuses)
            rec.spent = sum(bonuses.mapped('total_cost'))
            judged = bonuses.filtered(lambda b: b.outcome)
            ok = judged.filtered(lambda b: b.outcome in ('good', 'great'))
            rec.outcome_rate = (
                "%d de %d" % (len(ok), len(judged)) if judged else "—")
            rec.outcome_pct = (len(ok) / len(judged) * 100.0) if judged else 0.0


    def action_view_members(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'product.bonus.list.member',
            'view_mode': 'list,form',
            'domain': [('list_id', '=', self.id)],
            'context': {'default_list_id': self.id},
        }

    def action_view_bonuses(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'product.bonus',
            'view_mode': 'list,form',
            'domain': [('list_id', '=', self.id)],
        }

    @api.model
    def action_combine(self):
        """Multi-select in the list view -> combine into a new one."""
        lists = self.browse(self.env.context.get('active_ids', []))
        return {
            'type': 'ir.actions.act_window',
            'name': "Combinar listas",
            'res_model': 'product.bonus.list.combine',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_list_ids': [(6, 0, lists.ids)]},
        }

    def action_open_triage(self):
        """Open a new dispatch with this list already loaded.

        Pointed at product.bonus.triage until now -- a model deleted when the
        wizard became the dispatch. The button had been dead since, and no test
        clicked it: a broken button is invisible to a suite that only calls
        methods.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Enviar bonificação",
            'res_model': 'product.bonus.dispatch',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_list_ids': [(6, 0, [self.id])]},
        }

    def action_open_import(self):
        """Importar direto para ESTA lista."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Importar contatos"),
            'res_model': 'product.bonus.list.import',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_list_id': self.id},
        }

    def action_open_add_members(self):
        """O mesmo assistente, a partir da lista.

        A porta principal é Contatos > filtrar > Ação, onde estão os filtros
        bons. Mas quem já está com a lista aberta não deveria ter que sair dela
        para acrescentar meia dúzia de nomes.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Adicionar contatos"),
            'res_model': 'product.bonus.list.add',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_list_id': self.id},
        }

class ProductBonusListMember(models.Model):
    """A model, not an m2m.

    An m2m knows who is on the list *today*. He wants to know who joined, when
    and by whom -- that is the difference between a tag and a record.
    """
    _name = 'product.bonus.list.member'
    _description = 'VIP List Member'
    _order = 'list_id, partner_id'
    _rec_name = 'partner_id'

    list_id = fields.Many2one(
        'product.bonus.list', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one(
        'res.partner', required=True, ondelete='cascade', index=True)
    joined_on = fields.Date(default=fields.Date.context_today, readonly=True)
    left_on = fields.Date(readonly=True)
    added_by_id = fields.Many2one(
        'res.users', readonly=True, default=lambda s: s.env.user)
    active = fields.Boolean(default=True)
    note = fields.Char()

    # A mesma nota do disparo, aqui: a lista VIP é onde o público é CURADO, e
    # curar sem ver o retorno é como escolher no escuro e descobrir depois.
    # Armazenado porque o pivô agrupa por ele: relacionado não armazenado não
    # entra em GROUP BY.
    partner_type = fields.Selection(
        related='partner_id.bonus_partner_type', string="Tipo", store=True)
    partner_bio = fields.Char(
        related='partner_id.bonus_bio', string="Who they are")
    rating_label = fields.Char(
        related='partner_id.bonus_rating_label', string="Score",
        help=SCORE_HELP)
    rating_html = fields.Html(
        related='partner_id.bonus_rating_html', string="Score",
        sanitize=False, help=SCORE_HELP)
    rating_band = fields.Selection(
        related='partner_id.bonus_rating_band', string="Situação")

    _list_partner_uniq = models.Constraint(
        'unique(list_id, partner_id)',
        'This contact is already on the list.',
    )

    def action_leave(self):
        self.write({'active': False})

    def write(self, vals):
        """Quem carimba a saída é o CAMPO active, não o botão.

        "o que é esse Saiu em?" -- a data em que a pessoa saiu da lista, o par
        de "Entrou em". Estava sempre vazia, e por um motivo: só o botão "Saiu"
        da tela avulsa de membros a preenchia. Na aba Membros da lista -- onde
        se trabalha de verdade -- tira-se alguém pelo toggle Ativo, e a data
        não era gravada. A lista é um modelo, e não um m2m, justamente para ter
        essa história; perdê-la esvazia a razão de ser do modelo.
        """
        if 'active' in vals:
            vals = dict(vals)
            if vals['active']:
                vals.setdefault('left_on', False)       # voltou
            else:
                vals.setdefault('left_on', fields.Date.context_today(self))
        return super().write(vals)
