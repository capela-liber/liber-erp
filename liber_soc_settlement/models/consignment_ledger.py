# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class ConsignmentLedger(models.Model):
    """The shelf ledger: one row per movement, in and out of every customer's
    consignment shelf, from BOTH worlds.

    Odoo's stock is the truth going forward. The imported NFe is a migration
    bridge: for the five companies being migrated, most of the history exists
    only as fiscal documents, and Odoo's shelf was seeded with a flat inventory
    adjustment that erased the story (when each title went, when it sold, how
    long it sat).

    So the two sources are NOT merged into one number here -- that is exactly
    the trap that made a CO line read 'Sales 13 / Sold 0'. They are stacked side
    by side with `source` on every row, so grouping by source shows the gap, and
    the gap closes on its own as the settlements are really run in Odoo.
    """
    _name = 'consignment.ledger'
    _description = 'Consignment Shelf Ledger'
    _auto = False
    _order = 'date desc, id desc'
    _rec_name = 'product_id'

    date = fields.Date(string='Date', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    product_id = fields.Many2one('product.product', string='Title', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    source = fields.Selection([
        ('stock', 'Odoo stock'),
        ('fiscal', 'Fiscal (NFe)'),
    ], string='Source', readonly=True)
    kind = fields.Selection([
        ('ship', 'Shipment'),
        ('sale', 'Sale'),
        ('return', 'Return'),
    ], string='Movement', readonly=True)
    quantity = fields.Float(
        string='Balance', readonly=True, aggregator='sum',
        help="Signed: a shipment adds to the shelf, a sale or a return takes "
             "off it. Summing a period gives the shelf balance for that period.")
    qty_in = fields.Float(string='In', readonly=True, aggregator='sum')
    qty_out = fields.Float(string='Out', readonly=True, aggregator='sum')
    document = fields.Char(string='Document', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                -- The id MUST be derived from the source row's primary key, never
                -- from ROW_NUMBER(): Odoo searches (collecting ids) and then reads
                -- (re-fetching by id) in two separate evaluations of this view, and
                -- a row number is not stable across them when rows tie on the ORDER
                -- BY -- the ids would silently land on different rows and mix up
                -- customers. Even ids = stock moves, odd = fiscal items.
                SELECT * FROM (
                    -- 1) What Odoo's stock ledger knows: real moves in and out
                    --    of a consignment shelf.
                    SELECT
                        sm.id * 2                           AS id,
                        sm.date::date                       AS date,
                        COALESCE(dst.consignment_partner_id,
                                 src.consignment_partner_id) AS partner_id,
                        sm.product_id                       AS product_id,
                        sm.company_id                       AS company_id,
                        'stock'                             AS source,
                        CASE
                            WHEN COALESCE(dst.is_consignment_shelf, FALSE) THEN 'ship'
                            WHEN dst.usage = 'customer'   THEN 'sale'
                            ELSE 'return'
                        END                                 AS kind,
                        CASE WHEN COALESCE(dst.is_consignment_shelf, FALSE)
                             THEN sm.quantity ELSE -sm.quantity END AS quantity,
                        CASE WHEN COALESCE(dst.is_consignment_shelf, FALSE)
                             THEN sm.quantity ELSE 0 END    AS qty_in,
                        CASE WHEN COALESCE(dst.is_consignment_shelf, FALSE)
                             THEN 0 ELSE sm.quantity END    AS qty_out,
                        sm.reference                        AS document
                    FROM stock_move sm
                    JOIN stock_location src ON src.id = sm.location_id
                    JOIN stock_location dst ON dst.id = sm.location_dest_id
                    -- COALESCE, not the bare column: Odoo stores an unset
                    -- boolean as NULL, and `NOT (TRUE AND NULL)` is NULL, which
                    -- silently drops the row instead of keeping it.
                    WHERE sm.state = 'done'
                      AND (COALESCE(dst.is_consignment_shelf, FALSE)
                           OR COALESCE(src.is_consignment_shelf, FALSE))
                      -- a shelf-to-shelf move is not a shelf event, it is a
                      -- transfer between two customers; ignore it here
                      AND NOT (COALESCE(dst.is_consignment_shelf, FALSE)
                               AND COALESCE(src.is_consignment_shelf, FALSE))

                    UNION ALL

                    -- 2) What the fiscal documents know. The CFOP already says
                    --    what each note does to the shelf (nfe.cfop
                    --    consignment_effect), so no guessing here.
                    SELECT
                        it.id * 2 + 1                       AS id,
                        p.file_create_date                  AS date,
                        p.partner_id                        AS partner_id,
                        it.ks_product_id                    AS product_id,
                        p.company_id                        AS company_id,
                        'fiscal'                            AS source,
                        c.consignment_effect                AS kind,
                        CASE WHEN c.consignment_effect = 'ship'
                             THEN it.ks_product_qty
                             ELSE -it.ks_product_qty END    AS quantity,
                        CASE WHEN c.consignment_effect = 'ship'
                             THEN it.ks_product_qty ELSE 0 END AS qty_in,
                        CASE WHEN c.consignment_effect = 'ship'
                             THEN 0 ELSE it.ks_product_qty END AS qty_out,
                        p.danfe_no                          AS document
                    FROM nfe_xml_items it
                    JOIN nfe_xml_panel p ON p.id = it.soc_xml_id
                    JOIN nfe_cfop c      ON c.id = p.cfop_id
                    WHERE COALESCE(p.is_cancelled, FALSE) = FALSE
                      AND it.ks_product_id IS NOT NULL
                      AND p.partner_id IS NOT NULL
                      AND p.file_create_date IS NOT NULL
                      AND c.consignment_effect IN ('ship', 'sale', 'return')
                      -- Only customers who actually HAVE a shelf. This is a shelf
                      -- ledger: the stock side is shelf-scoped by construction, so
                      -- the fiscal side must be too. Without it, a plain outright
                      -- sale (CFOP 5102) to a customer who never consigned anything
                      -- lands here as a shelf decrement -- the FNDE, who buys
                      -- direct, showed up "taking 41k units off" a shelf that never
                      -- existed.
                      -- EXISTS, not a JOIN: a customer can own more than one shelf
                      -- location, and a join would emit the same NFe item once per
                      -- location, doubling every quantity.
                      AND EXISTS (
                          SELECT 1 FROM stock_location shelf
                          WHERE shelf.consignment_partner_id = p.partner_id
                            AND COALESCE(shelf.is_consignment_shelf, FALSE)
                      )
                ) ledger
            )
        """ % self._table)
