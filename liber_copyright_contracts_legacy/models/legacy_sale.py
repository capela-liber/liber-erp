# -*- coding: utf-8 -*-
"""The unified legacy sales base, one record per invoice line.

Half a million rows: everything that touches the whole table goes through
SQL (COPY for the import, UPDATE ... FROM for the product link and the
classification). The ORM is used for what people do by hand -- fixing one
row's effect, forcing a line in or out -- and those writes re-run the same
classification on just those rows, so both paths agree by construction."""
import csv
import io
import logging
import os
import tempfile
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .legacy_cfop import EFFECTS

_logger = logging.getLogger(__name__)

# CSV header of the unified base -> column of this table. The import refuses
# a file whose header does not carry every key: a renamed column would
# otherwise land silently as NULL in a money field.
CSV_COLUMNS = {
    "fonte": "source",
    "nf": "nf",
    "data_emissao": "date",
    "ano": "year",
    "mes": "month",
    "cnpj_cpf": "partner_vat",
    "cliente": "partner_name",
    "isbn_ean": "isbn",
    "codigo_interno": "internal_code",
    "titulo": "title",
    "titulo_original": "title_original",
    "autor": "author_name",
    "editora_selo": "imprint",
    "quantidade": "quantity",
    "qtde_origem": "quantity_origin",
    "preco_capa": "list_price",
    "valor_bruto": "amount_gross",
    "desconto": "discount",
    "valor_liquido": "amount_net",
    "valor_liquido_estimado": "amount_net_estimated",
    "valor_total_nota": "note_total",
    "cfop": "cfop",
    "cfop_descricao": "cfop_description",
    "natureza_operacao": "nature",
    "status_nf": "nf_status",
    "flags": "flags",
}
NUMERIC = {"quantity", "list_price", "amount_gross", "discount", "amount_net",
           "amount_net_estimated", "note_total"}
INTEGER = {"year", "month"}
DATES = {"date"}

# Quality flags of the unification that take a row out of the accrual by
# default. The person can still force a row in (``force_include``).
EXCLUDING_FLAGS = (
    ("NF_SEM_EFEITO_FISCAL", "Cancelled or never issued"),
    ("QTDE_NAO_CONFIAVEL", "Quantity not reliable"),
    ("VALOR_PODE_SER_TOTAL_DA_NOTA", "Amount may be the whole invoice"),
    ("POSSIVEL_DUPLICATA_EXATA", "Possible exact duplicate"),
    ("QTDE_ZERO_OU_NEGATIVA", "Zero or negative quantity"),
    ("LINHA_PARCIALMENTE_CORROMPIDA", "Partially corrupted row"),
)
IMPORT_BATCH = 20000

# The discount in %, from the same net and gross the royalty bases use.
# Zero when there is no gross to compare with, or when the net is above it
# (a price raise is not a discount). Shared with the migration.
DISCOUNT_PERCENT_SQL = """
    CASE WHEN COALESCE(s.amount_gross, 0) > 0
          AND COALESCE(s.amount_net_estimated, s.amount_net) IS NOT NULL
         THEN GREATEST(0, round((1 - COALESCE(s.amount_net_estimated,
                                              s.amount_net)
                                 / s.amount_gross)::numeric * 100, 2))
         ELSE 0 END"""


class EdlabLegacySale(models.Model):
    _name = "edlab.legacy.sale"
    _description = "Legacy Sale (before Odoo)"
    _order = "date, source, nf, sequence"

    # --- as imported -------------------------------------------------
    sequence = fields.Integer(help="Row number in the imported file.")
    source = fields.Char(index=True, help="System the row came from.")
    nf = fields.Char(string="Invoice no.", index=True)
    date = fields.Date(index=True)
    year = fields.Integer(index=True)
    month = fields.Integer()
    partner_vat = fields.Char(string="Customer CNPJ/CPF")
    partner_name = fields.Char(string="Customer")
    isbn = fields.Char(string="ISBN/EAN", index=True)
    internal_code = fields.Char()
    title = fields.Char()
    title_original = fields.Char()
    author_name = fields.Char(string="Author (as written)")
    imprint = fields.Char(string="Publisher / imprint")
    quantity = fields.Float(digits=(16, 2))
    quantity_origin = fields.Char(
        help="INFORMADA, ESTIMADA, NAO_DISPONIVEL or NAO_CONFIAVEL.")
    list_price = fields.Float(string="Cover price", digits=(16, 2))
    amount_gross = fields.Float(string="Gross (qty x cover)", digits=(16, 2))
    discount = fields.Float(digits=(16, 2))
    amount_net = fields.Float(string="Net (invoice line)", digits=(16, 2))
    amount_net_estimated = fields.Float(
        string="Net (estimated)", digits=(16, 2),
        help="Net amount; where the source only had the invoice total "
        "(Galba), the total prorated over the lines by gross amount.")
    note_total = fields.Float(
        string="Invoice total", digits=(16, 2),
        help="Total of the WHOLE invoice, repeated on each of its lines. "
        "Never sum it by line.")
    cfop = fields.Char(string="CFOP", size=4, index=True)
    cfop_description = fields.Char(string="CFOP description")
    nature = fields.Char(string="Operation")
    nf_status = fields.Char(string="Invoice status")
    flags = fields.Char(help="Quality flags of the unification, ';'-separated.")
    company_id = fields.Many2one(
        "res.company", required=True, index=True,
        default=lambda self: self.env.company)

    # --- resolved here -----------------------------------------------
    product_id = fields.Many2one(
        "product.product", index=True, ondelete="set null",
        help="Linked by ISBN at import (barcode, ISBN or internal reference "
        "of the product); set by hand on the rows the ISBN did not reach.")
    product_tmpl_id = fields.Many2one(
        related="product_id.product_tmpl_id", store=True, index=True)
    cfop_id = fields.Many2one("edlab.legacy.cfop", string="CFOP (table)",
                              ondelete="set null", index=True)
    effect = fields.Selection(
        EFFECTS, index=True, readonly=True,
        help="From the CFOP table; from the operation wording when the row "
        "has no CFOP; from 'Effect (manual)' when set.")
    effect_manual = fields.Selection(
        EFFECTS, string="Effect (manual)",
        help="Overrides the effect derived from the CFOP for this row only.")
    excluded = fields.Boolean(
        readonly=True,
        help="Taken out of the accrual by a quality flag of the unification.")
    exclusion_reason = fields.Char(readonly=True)
    force_include = fields.Boolean(
        help="Count this row even though a quality flag excludes it.")
    force_exclude = fields.Boolean(
        help="Never count this row, whatever the CFOP says.")
    counts = fields.Boolean(
        string="Counts for royalties", index=True, readonly=True,
        help="Sale or return, linked to a product, not excluded: this is "
        "what the contracts accrue on.")
    signed_quantity = fields.Float(digits=(16, 2), readonly=True)
    royalty_base = fields.Float(
        string="Royalty base (net)", digits=(16, 2), readonly=True,
        help="Net amount with the sign of the effect (returns negative).")
    royalty_base_gross = fields.Float(
        string="Royalty base (gross)", digits=(16, 2), readonly=True)

    # --- special sales -----------------------------------------------
    # The base carries no channel: the royalties department sets it by
    # hand, a customer or an invoice at a time, in the list (multi-edit).
    team_id = fields.Many2one(
        "crm.team", string="Sales Channel", index=True, ondelete="set null",
        help="Channel of the sale, set by the royalties department. A sale "
        "from one of the company's special sales channels, with a discount "
        "at or above the minimum, is a special sale: contracts on the cover "
        "price pay it on the net amount -- the same rule as the invoices.")
    discount_percent = fields.Float(
        string="Discount (%)", digits=(16, 2), readonly=True,
        help="1 - net / gross: the discount the special-sale minimum is "
        "compared with. The base keeps the discount in money, not in %.")
    special_sale = fields.Boolean(
        compute="_compute_special_sale", search="_search_special_sale",
        help="Special sale under the current company's settings (Settings > "
        "Copyright): special channel and discount at or above the minimum.")

    @api.depends("source", "nf", "title")
    def _compute_display_name(self):
        for sale in self:
            sale.display_name = "%s %s - %s" % (
                sale.source or "", sale.nf or "", sale.title or "")

    @api.depends("team_id", "discount_percent")
    @api.depends_context("company")
    def _compute_special_sale(self):
        company = self.env.company
        for sale in self:
            sale.special_sale = sale._is_special_for(company)

    def _is_special_for(self, company):
        """The invoices' rule (liber_copyright_contracts_analytics), on a
        legacy row: no special channel configured means nothing is special."""
        self.ensure_one()
        teams = company.contract_special_sales_team_ids
        return bool(teams and self.team_id in teams
                    and self.discount_percent >= company.contract_special_min_discount)

    def _search_special_sale(self, operator, value):
        # The web client and Odoo 19's domain normalization send '=', '!='
        # or 'in'/'not in' over booleans: reduce them to the set wanted.
        if operator in ("=", "!="):
            wanted = {bool(value) == (operator == "=")}
        elif operator in ("in", "not in"):
            values = {bool(v) for v in value}
            wanted = values if operator == "in" else {True, False} - values
        else:
            raise UserError(_("Unsupported search on special sale."))
        if wanted == {True, False}:
            return []
        if not wanted:
            return [("id", "=", False)]
        company = self.env.company
        teams = company.contract_special_sales_team_ids
        if not teams:
            return [("id", "=", False)] if True in wanted else []
        special = ["&", ("team_id", "in", teams.ids),
                   ("discount_percent", ">=", company.contract_special_min_discount)]
        return special if True in wanted else ["!", *special]

    # ------------------------------------------------------------------
    # Manual edits re-run the classification on the touched rows
    # ------------------------------------------------------------------
    def write(self, vals):
        res = super().write(vals)
        if {"effect_manual", "force_include", "force_exclude", "product_id",
                "cfop", "flags", "quantity", "amount_net",
                "amount_net_estimated", "amount_gross"} & set(vals):
            self._classify()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if records:
            records._link_products()
            records._classify()
        return records

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------
    @api.model
    def _import_file(self, path, company=None, replace=True):
        """Load the unified base (``.csv`` or ``.xlsx``) for ``company``.

        ``replace`` wipes the company's previous rows first: the base is a
        snapshot, and re-importing it is how a corrected unification gets in.
        Returns the number of rows loaded."""
        company = company or self.env.company
        if not os.path.isfile(path):
            raise UserError(_("File not found on the server: %s", path))
        if replace:
            # SQL on purpose: half a million rows through the ORM's unlink
            # would take minutes for a table nothing else points to.
            self.env.cr.execute(
                "DELETE FROM edlab_legacy_sale WHERE company_id = %s",
                (company.id,))
            self.env.invalidate_all()
        if path.lower().endswith((".xlsx", ".xlsm")):
            rows = self._rows_from_xlsx(path)
        else:
            rows = self._rows_from_csv(path)
        header = next(rows)
        missing = [c for c in CSV_COLUMNS if c not in header]
        if missing:
            raise UserError(_(
                "The file does not look like the unified base: column(s) %s "
                "missing from the header.", ", ".join(missing)))
        t0 = time.monotonic()
        total = self._copy_rows(header, rows, company)
        t1 = time.monotonic()
        self._link_products()
        t2 = time.monotonic()
        self._classify()
        t3 = time.monotonic()
        _logger.info(
            "Legacy sales: %s row(s) imported for %s from %s "
            "(copy %.0fs, product link %.0fs, classification %.0fs)",
            total, company.name, path, t1 - t0, t2 - t1, t3 - t2)
        return total

    @staticmethod
    def _rows_from_csv(path):
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for row in csv.reader(handle):
                yield row

    @staticmethod
    def _rows_from_xlsx(path, sheet="BASE_UNIFICADA"):
        import openpyxl  # noqa: PLC0415 -- heavy, only for the xlsx path
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = book[sheet] if sheet in book.sheetnames else book.worksheets[0]
        for row in ws.iter_rows(values_only=True):
            yield ["" if v is None else
                   (v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else str(v))
                   for v in row]
        book.close()

    def _copy_rows(self, header, rows, company):
        """Stream the rows into the table with COPY, in batches, casting as
        we go. Everything is text in the staging table; the INSERT does the
        casts with NULLIF so an empty cell becomes NULL, not zero."""
        cr = self.env.cr
        positions = {csv_name: header.index(csv_name) for csv_name in CSV_COLUMNS}
        cols = list(CSV_COLUMNS.values())
        cr.execute("CREATE TEMP TABLE edlab_legacy_stage (seq integer, %s) "
                   "ON COMMIT DROP" % ", ".join("%s text" % c for c in cols))
        uid = self.env.uid
        total = 0

        def flush(buffer):
            buffer.seek(0)
            cr.copy_expert(
                "COPY edlab_legacy_stage (seq, %s) FROM STDIN WITH (FORMAT csv)"
                % ", ".join(cols), buffer)
            casts = []
            for c in cols:
                if c in NUMERIC:
                    casts.append("NULLIF(%s, '')::numeric" % c)
                elif c in INTEGER:
                    casts.append("NULLIF(%s, '')::numeric::integer" % c)
                elif c in DATES:
                    casts.append("NULLIF(%s, '')::date" % c)
                elif c == "cfop":
                    casts.append("CASE WHEN %s ~ '^\\d{4}(\\.0)?$' "
                                 "THEN left(%s, 4) END" % (c, c))
                else:
                    casts.append("NULLIF(%s, '')" % c)
            # Booleans are born FALSE, not NULL: a NULL force_exclude would
            # turn "NOT force_exclude" into NULL and no row would ever count.
            cr.execute(
                "INSERT INTO edlab_legacy_sale (sequence, %s, company_id, "
                "excluded, force_include, force_exclude, counts, "
                "create_uid, create_date, write_uid, write_date) "
                "SELECT seq, %s, %%s, false, false, false, false, "
                "%%s, now(), %%s, now() FROM edlab_legacy_stage"
                % (", ".join(cols), ", ".join(casts)), (company.id, uid, uid))
            cr.execute("TRUNCATE edlab_legacy_stage")

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        count = 0
        for seq, row in enumerate(rows, start=2):
            if not any(cell.strip() for cell in row if cell):
                continue
            writer.writerow([seq] + [(row[positions[c]] if positions[c] < len(row)
                                      else "").strip() for c in CSV_COLUMNS])
            count += 1
            if count >= IMPORT_BATCH:
                flush(buffer)
                total += count
                buffer = io.StringIO()
                writer = csv.writer(buffer)
                count = 0
        if count:
            flush(buffer)
            total += count
        cr.execute("DROP TABLE IF EXISTS edlab_legacy_stage")
        self.env.invalidate_all()
        return total

    @api.model
    def _import_binary(self, data, filename, company=None, replace=True):
        """Wizard path: write the upload to a temp file and import it."""
        suffix = ".xlsx" if filename.lower().endswith((".xlsx", ".xlsm")) else ".csv"
        handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            handle.write(data)
            handle.close()
            return self._import_file(handle.name, company=company, replace=replace)
        finally:
            os.unlink(handle.name)

    # ------------------------------------------------------------------
    # Product link and classification (SQL, whole table or given rows)
    # ------------------------------------------------------------------
    def _where_ids(self):
        """SQL fragment restricting to ``self`` when it is a real recordset,
        or to every row when called on the empty model."""
        if self.ids:
            return " AND s.id IN %s", (tuple(self.ids),)
        return "", ()

    def _link_products(self):
        """Match the ISBN against the product's barcode, ISBN field (when the
        catalogue module provides one) or internal reference. Rows that
        already have a product keep it: a manual link survives a re-run."""
        # Pending ORM writes (a product set by hand) must reach the table
        # before the SQL below reads it.
        self.env.flush_all()
        cr = self.env.cr
        where, params = self._where_ids()
        joins = ["pp.barcode = s.isbn", "pp.default_code = s.isbn"]
        if "isbn" in self.env["product.template"]._fields:
            joins.append("pt.isbn = s.isbn")
        cr.execute("""
            UPDATE edlab_legacy_sale s SET product_id = m.product_id
            FROM (
                SELECT s.id AS sale_id, min(pp.id) AS product_id
                FROM edlab_legacy_sale s
                JOIN product_product pp
                  JOIN product_template pt ON pt.id = pp.product_tmpl_id
                  ON (%s)
                WHERE s.product_id IS NULL AND s.isbn IS NOT NULL %s
                GROUP BY s.id
            ) m WHERE m.sale_id = s.id
        """ % (" OR ".join(joins), where), params)
        # product_tmpl_id is a stored related: keep it in step without an
        # ORM recompute over half a million rows.
        cr.execute("""
            UPDATE edlab_legacy_sale s SET product_tmpl_id = pp.product_tmpl_id
            FROM product_product pp
            WHERE pp.id = s.product_id
              AND s.product_tmpl_id IS DISTINCT FROM pp.product_tmpl_id %s
        """ % where, params)
        cr.execute("UPDATE edlab_legacy_sale s SET product_tmpl_id = NULL "
                   "WHERE s.product_id IS NULL AND s.product_tmpl_id IS NOT NULL"
                   + where, params)
        self.env.invalidate_all()

    def _classify(self):
        """Effect, exclusion and signed bases, in one UPDATE.

        Effect: manual > CFOP table > operation wording > neutral.
        Excluded: any of the EXCLUDING_FLAGS in ``flags``.
        Counts: effect is sale/return AND product linked AND
        (not excluded OR forced in) AND not forced out."""
        self.env.flush_all()
        cr = self.env.cr
        where, params = self._where_ids()
        reason_case = " ".join(
            "WHEN s.flags ILIKE %s THEN %s" for _flag in EXCLUDING_FLAGS)
        reason_params = []
        for flag, label in EXCLUDING_FLAGS:
            reason_params += ["%%%s%%" % flag, label]
        from .legacy_cfop import NATURE_RULES  # noqa: PLC0415
        nature_case = " ".join(
            "WHEN s.nature ~* %s THEN %s" for _rule in NATURE_RULES)
        nature_params = []
        for pattern, effect in NATURE_RULES:
            nature_params += [pattern.pattern, effect]
        cr.execute("""
            UPDATE edlab_legacy_sale s SET
                cfop_id = c.id,
                effect = COALESCE(s.effect_manual, c.effect,
                                  CASE %(nature_case)s ELSE 'neutral' END),
                exclusion_reason = CASE %(reason_case)s ELSE NULL END
            FROM edlab_legacy_sale s2
            LEFT JOIN edlab_legacy_cfop c ON c.code = s2.cfop AND c.active
            WHERE s2.id = s.id %(where)s
        """ % {"nature_case": nature_case, "reason_case": reason_case,
               "where": where},
            tuple(nature_params + reason_params) + params)
        cr.execute("""
            UPDATE edlab_legacy_sale s SET
                excluded = (s.exclusion_reason IS NOT NULL),
                counts = (s.effect IN ('sale', 'return')
                          AND s.product_id IS NOT NULL
                          AND (s.exclusion_reason IS NULL
                               OR COALESCE(s.force_include, false))
                          AND NOT COALESCE(s.force_exclude, false)),
                signed_quantity = sign * COALESCE(s.quantity, 0),
                royalty_base = sign * COALESCE(s.amount_net_estimated,
                                               s.amount_net, s.amount_gross, 0),
                royalty_base_gross = sign * COALESCE(s.amount_gross,
                                                     s.amount_net_estimated,
                                                     s.amount_net, 0),
                discount_percent = %(discount)s
            FROM (SELECT id, CASE WHEN effect = 'return' THEN -1 ELSE 1 END AS sign
                  FROM edlab_legacy_sale) x
            WHERE x.id = s.id %(where)s
        """ % {"where": where, "discount": DISCOUNT_PERCENT_SQL}, params)
        self.env.invalidate_all()

    @api.model
    def action_reclassify_all(self):
        """Server action: re-run the link and the classification over the
        whole table (after editing the CFOP table or creating products)."""
        self._link_products()
        self._classify()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Legacy sales"),
                       "message": _("Products linked and rows reclassified."),
                       "type": "success"},
        }

    # ------------------------------------------------------------------
    # Aggregation for the contracts
    # ------------------------------------------------------------------
    @api.model
    def _monthly_totals(self, product_tmpl, date_from=None, date_to=None,
                        company=None):
        """Per month, the counted copies and bases of a work, oldest first.

        Returns a list of dicts ``{month: date(first day), qty, base_net,
        base_gross, base_sales_price}``. ``base_sales_price`` is what a
        contract on the cover price pays on: the gross, except on the
        special sales of ``company`` (the contract's), which pay on the net.
        Read with sudo: the contract company may differ from the company
        the base was imported under."""
        # Raw SQL below: a channel just set by the ORM must be in the table.
        self.env.flush_all()
        cr = self.env.cr
        teams = company.contract_special_sales_team_ids if company else None
        special = "false"
        special_params = []
        if teams:
            special = "(s.team_id = ANY(%s) AND s.discount_percent >= %s)"
            special_params = [teams.ids, company.contract_special_min_discount]
        params = special_params + [product_tmpl.id]
        extra = ""
        if date_from:
            extra += " AND s.date >= %s"
            params.append(date_from)
        if date_to:
            extra += " AND s.date <= %s"
            params.append(date_to)
        cr.execute("""
            SELECT date_trunc('month', s.date)::date AS month,
                   sum(s.signed_quantity), sum(s.royalty_base),
                   sum(s.royalty_base_gross),
                   sum(CASE WHEN %s THEN s.royalty_base
                            ELSE s.royalty_base_gross END)
            FROM edlab_legacy_sale s
            WHERE s.counts AND s.product_tmpl_id = %%s AND s.date IS NOT NULL %s
            GROUP BY 1 ORDER BY 1
        """ % (special, extra), params)
        return [{"month": month, "qty": float(qty or 0),
                 "base_net": float(net or 0), "base_gross": float(gross or 0),
                 "base_sales_price": float(price or 0)}
                for month, qty, net, gross, price in cr.fetchall()]
