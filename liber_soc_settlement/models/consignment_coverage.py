# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class ConsignmentCoverage(models.Model):
    """What each campaign asked for, against what actually reached the customer.

    The Inventory report is stock.quant: it can only show a title that is (or was)
    physically on a shelf. A title a campaign wants but the customer NEVER received
    has no quant row, so it is invisible there. Yet that gap -- the unexplored
    universe -- is exactly what a campaign manager needs: who never got anything,
    which book never reached which customer.

    So this report is the UNION of two sources, per (customer, channel, title):

      - the target: the running campaigns of the customer's channel, resolved by
        the SAME highest-target-wins rule the acerto uses -- max per title within
        a channel (see consignment.settlement._running_campaigns);
      - the shelf: stock.quant on the customer's consignment shelf (may be absent).

    qty_short = the target not yet covered. "Never received" is its sharpest cut:
    qty_on_shelf = 0 while qty_target > 0 -- the title the campaign wants and the
    customer has none of.

    _auto = False: a read-only SQL view, like sale.report. Filter it by "Never
    received" and group by Customer to read the universe still to be explored.
    """
    _name = 'consignment.coverage'
    _description = 'Campaign Coverage'
    _auto = False
    _rec_name = 'product_id'
    _order = 'qty_short desc'

    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    team_id = fields.Many2one('crm.team', string='Sales Channel', readonly=True)
    product_id = fields.Many2one('product.product', string='Title', readonly=True)
    campaign_id = fields.Many2one(
        'consignment.template', string='Campaign', readonly=True,
        help="The running campaign that set this title's target. When two "
             "campaigns of the channel ask for the same title, it is the one "
             "with the highest ask -- the same target that wins the acerto. "
             "Empty on a title on the shelf that no running campaign asks for.")
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    qty_on_shelf = fields.Integer(string='On Shelf', readonly=True)
    qty_target = fields.Integer(string='Target', readonly=True)
    qty_short = fields.Integer(string='Short', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE VIEW {self._table} AS (
                WITH shelf AS (
                    SELECT
                        q.consignment_partner_id AS partner_id,
                        q.consignment_team_id    AS team_id,
                        q.product_id             AS product_id,
                        q.company_id             AS company_id,
                        SUM(q.quantity)          AS qty_on_shelf
                    FROM stock_quant q
                    JOIN stock_location l ON l.id = q.location_id
                    WHERE l.is_consignment_shelf = TRUE
                      AND q.consignment_partner_id IS NOT NULL
                    GROUP BY q.consignment_partner_id, q.consignment_team_id,
                             q.product_id, q.company_id
                ),
                target AS (
                    -- One row per (customer, channel, title): the campaign with
                    -- the highest ask wins the target AND is named as its owner,
                    -- so the grain never doubles when campaigns overlap.
                    SELECT DISTINCT ON (a.partner_id, a.team_id, tl.product_id)
                        a.partner_id            AS partner_id,
                        a.team_id               AS team_id,
                        tl.product_id           AS product_id,
                        a.company_id            AS company_id,
                        tl.product_uom_qty      AS qty_target,
                        t.id                    AS campaign_id
                    FROM consignment_agreement a
                    JOIN consignment_template t
                         ON t.team_id = a.team_id AND t.is_running = TRUE
                    JOIN consignment_template_line tl
                         ON tl.template_id = t.id
                    WHERE a.state = 'active' AND a.team_id IS NOT NULL
                    ORDER BY a.partner_id, a.team_id, tl.product_id,
                             tl.product_uom_qty DESC, t.id
                )
                SELECT
                    row_number() OVER ()                        AS id,
                    COALESCE(s.partner_id, t.partner_id)        AS partner_id,
                    COALESCE(s.team_id, t.team_id)              AS team_id,
                    COALESCE(s.product_id, t.product_id)        AS product_id,
                    t.campaign_id                               AS campaign_id,
                    COALESCE(s.company_id, t.company_id)        AS company_id,
                    COALESCE(ROUND(s.qty_on_shelf), 0)::integer AS qty_on_shelf,
                    COALESCE(t.qty_target, 0)                   AS qty_target,
                    GREATEST(COALESCE(t.qty_target, 0)
                             - COALESCE(ROUND(s.qty_on_shelf), 0), 0)::integer
                                                                AS qty_short
                FROM shelf s
                FULL OUTER JOIN target t
                  ON  s.partner_id = t.partner_id
                  AND s.team_id    = t.team_id
                  AND s.product_id = t.product_id
            )
        """)
