# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .bonus_quota import DEFAULT_SPLIT
from .bonus_rating import DEFAULT_HALF_LIFE, DEFAULT_POINTS, DEFAULT_TEST_SIZE


class ResConfigSettings(models.TransientModel):
    """Where the donation percentage lives.

    He looked for it and could not find it, and he was right: the first cut only
    let you type a number of copies, per title, one row at a time. But the
    number he thinks in is "de uma tiragem de 3000 quero doar 5%" -- a
    percentage, and a house-wide one. Per-title rows are the exception, not the
    way in.
    """
    _inherit = 'res.config.settings'

    bonus_pct_editorial = fields.Float(
        string="Author / Editorial",
        config_parameter='product_bonus.pct_editorial',
        default=DEFAULT_SPLIT['editorial'])
    bonus_pct_marketing = fields.Float(
        string="Marketing",
        config_parameter='product_bonus.pct_marketing',
        default=DEFAULT_SPLIT['marketing'])
    bonus_pct_commercial = fields.Float(
        string="Commercial",
        config_parameter='product_bonus.pct_commercial',
        default=DEFAULT_SPLIT['commercial'])

    bonus_pct_total = fields.Float(
        string="Total", compute='_compute_bonus_pct_total')

    # Fiscal: which fiscal position is the bonus one (it must be auto-paid --
    # nfe_remessa settles the note on post) and its CFOP. The journal is the
    # shared REM/ journal; the accounts live in the fiscal position's mapping.
    bonus_fiscal_position_id = fields.Many2one(
        related='company_id.bonus_fiscal_position_id', readonly=False)
    bonus_cfop_id = fields.Many2one(
        related='company_id.bonus_cfop_id', readonly=False)

    # --- A nota do parceiro: os cortes são julgamento da casa ------------
    # Fibonacci porque os saltos crescem: "Arrasou" vale muito mais que
    # proporcionalmente mais, que é como funciona de verdade.
    bonus_points_silence = fields.Float(
        string="Silêncio", config_parameter='product_bonus.points_silence',
        default=DEFAULT_POINTS['silence'])
    bonus_points_weak = fields.Float(
        string="Meia-boca", config_parameter='product_bonus.points_weak',
        default=DEFAULT_POINTS['weak'])
    bonus_points_good = fields.Float(
        string="Divulgou", config_parameter='product_bonus.points_good',
        default=DEFAULT_POINTS['good'])
    bonus_points_great = fields.Float(
        string="Arrasou", config_parameter='product_bonus.points_great',
        default=DEFAULT_POINTS['great'])
    bonus_rating_test_size = fields.Integer(
        string="Avaliações para sair do teste",
        config_parameter='product_bonus.rating_test_size',
        default=DEFAULT_TEST_SIZE)
    bonus_rating_half_life = fields.Integer(
        string="Meia-vida da recência (meses)",
        config_parameter='product_bonus.rating_half_life',
        default=DEFAULT_HALF_LIFE)

    # X days after release, call to confirm arrival (a placeholder for a real
    # arrival estimate -- distance, carrier -- which comes later).
    bonus_days_to_call = fields.Integer(
        string="Days to call", config_parameter='product_bonus.days_to_call',
        default=10)

    def set_values(self):
        """Recalcula os scores quando a casa recalibra a régua.

        O score é armazenado (para poder ser ordenado) e depende destes
        parâmetros. Sem isto, mudar os pontos em Definições não mudaria nada na
        tela até cada pessoa receber outro livro -- a configuração pareceria
        quebrada, e a explicação ("é cache") não serve para ninguém.
        """
        res = super().set_values()
        self.env['res.partner']._cron_recompute_bonus_rating()
        return res

    @api.depends('bonus_pct_editorial', 'bonus_pct_marketing', 'bonus_pct_commercial')
    def _compute_bonus_pct_total(self):
        for rec in self:
            rec.bonus_pct_total = (rec.bonus_pct_editorial + rec.bonus_pct_marketing
                                   + rec.bonus_pct_commercial)
