# -*- coding: utf-8 -*-
"""The print-price ladder: what the printer charges, per print run.

This is the answer to "how do I see the price before committing to anything?".
Instead of a button that calls the API while somebody waits, a cron writes the
printer's ladder into `product.supplierinfo` -- the *native* Odoo vendor price
list, keyed by `min_qty`. From then on the price is simply there: type 50 on a
purchase line and Odoo resolves the 50-copy rate by itself, offline, with no
call on the critical path.

The mapping is one-to-one with Metabrasil's contract, which is why this fits
so cleanly:

    {"tiragem": 50, "valor": 7.50}   ->   supplierinfo(min_qty=50, price=7.50)

Two things the API cannot tell us directly, and how we get them anyway:

* **Is this book in their catalogue?** There is no endpoint for it, and
  /fretes is no help -- it happily quotes freight for an ISBN the printer
  rejects at order time. A price coming back IS the membership test, so the
  sweep stamps the configured tag on books that quote and removes it from
  books that stop.
* **What does it cost today?** /precificacao went live in 2026-07 and answers
  three different ways, which the sweep counts separately because they call
  for different actions: a price (store it), a 200 with zeros (the printer
  has the title but never priced it -- a negotiation), or a 400 saying the
  ISBN is not in the client repository (an upload). After the printer
  populated its catalogue on 27/07 the split went from 16 priced to 411 of
  675, with the zero-priced middle case disappearing entirely.

What this deliberately does NOT do is touch routes. Putting the Dropship route
on a book makes *every* sale of it dropship, stock or no stock (measured: a
title with 50 on hand still raised a purchase order and no delivery). Dropship
is the exception here, not the rule, so the route stays a human decision on
the never-stocked titles.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# One sweep of the whole catalogue is ~700 calls against an API that answers in
# about a second and sometimes times out: minutes of work, far too long to hold
# a browser. Anything longer than this many books goes to the cron instead.
INLINE_LIMIT = 50
# Books per commit. A sweep killed halfway keeps the prices it already found
# instead of rolling all of them back.
COMMIT_EVERY = 25

# Books per cron run. Odoo kills a cron job at `limit_time_real` -- 120s on
# this server -- and the full catalogue needs about five minutes, so a single
# run can never finish it. Each run takes a bite it can chew (~60 calls at
# roughly a second each, with room for one 30s timeout) and re-triggers itself
# while work remains, so the catalogue completes across a chain of short runs
# instead of dying at the same book forever.
CRON_BATCH = 60
# Only re-ask about a book this many days after the last attempt, so a chained
# run always moves forward instead of re-pricing what it just did.
REFRESH_AFTER_DAYS = 14

LOCK_PARAM = 'liber_metabrasil.price_sweep_started'
# Generous next to a ~60s batch, short enough that a killed run does not stall
# the chain for long.
LOCK_STALE_MINUTES = 15


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    metabrasil_price_date = fields.Datetime(
        string='Print Price Updated', copy=False, readonly=True,
        help="When a price last landed for this book. Old date with prices "
             "still listed means the last sweep got no answer for it.")
    metabrasil_price_check_date = fields.Datetime(
        string='Print Price Checked', copy=False, readonly=True,
        help="When the printer was last asked about this book, answer or "
             "not. This is what the sweep orders by, so every run advances "
             "instead of re-asking about the same first books.")

    # ------------------------------------------------------------------
    # Entry points: cron, Settings button, list action
    # ------------------------------------------------------------------
    @api.model
    def _cron_metabrasil_refresh_prices(self):
        """One batch of the catalogue, then re-trigger while work remains.

        Deliberately not "sweep everything": the cron is killed at 120s and
        the catalogue needs minutes, so a single-shot version would be
        murdered at the same place on every run and never reach the end.
        """
        stale = fields.Datetime.subtract(fields.Datetime.now(),
                                         days=REFRESH_AFTER_DAYS)
        # 'not in (False, "")' e não '!= False': em SQL o segundo vira
        # IS NOT NULL, que deixa passar o código de barras VAZIO. Um livro
        # assim atravessava o filtro e caía no ramo "sem ISBN" lá embaixo, que
        # segue sem carimbar data -- então voltava no lote seguinte, e no
        # seguinte, ocupando uma vaga para sempre.
        domain = ['&', ('barcode', 'not in', (False, '')),
                  '|', ('metabrasil_price_check_date', '=', False),
                       ('metabrasil_price_check_date', '<', stale)]
        domain += self._metabrasil_printable_domain()
        remaining = self.search_count(domain)
        if not remaining:
            _logger.info("Metabrasil price sweep: nothing stale to refresh.")
            return {'priced': 0, 'unpriced': 0, 'skipped': 0,
                    'no_price': 0, 'unknown': 0}
        books = self.search(domain, limit=CRON_BATCH,
                            order='metabrasil_price_check_date ASC NULLS FIRST, id')
        _logger.info("Metabrasil price sweep: batch of %s, %s stale in total.",
                     len(books), remaining)
        summary = books._metabrasil_refresh_prices(commit=True)
        if remaining > len(books) and not summary.get('busy'):
            cron = self.env.ref('liber_metabrasil.ir_cron_metabrasil_prices',
                                raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()
        return summary

    def _metabrasil_refresh_prices(self, commit=False):
        """Ask the printer for each book's ladder and store what comes back.

        Never raises: a sweep of hundreds must survive the one book that
        fails. Returns a summary dict for the caller to report.

        `commit` is for the cron only -- a long sweep saves as it goes, so
        being killed at book 500 keeps the 499 prices already found.
        """
        company = self.env.company
        summary = {'priced': 0, 'unpriced': 0, 'skipped': 0,
                   'no_price': 0, 'unknown': 0}
        if not company.metabrasil_enabled or not company.metabrasil_partner_id:
            _logger.info("Metabrasil price sweep skipped: not configured.")
            summary['skipped'] = len(self)
            return summary

        runs = company._metabrasil_print_run_list()
        if not runs:
            _logger.warning("Metabrasil price sweep skipped: no print runs "
                            "configured.")
            summary['skipped'] = len(self)
            return summary

        if not self._metabrasil_claim_sweep():
            # Somebody (or an impatient second click) is already sweeping.
            # Two sweeps double the load on their API and race each other
            # writing the same lines.
            summary['skipped'] = len(self)
            summary['busy'] = True
            return summary

        try:
            summary = self._metabrasil_sweep(runs, commit, summary)
        finally:
            self._metabrasil_release_sweep()
        _logger.info(
            "Metabrasil price sweep done: %(priced)s priced, %(no_price)s "
            "known but unpriced, %(unknown)s not in their catalogue, "
            "%(skipped)s skipped.", summary)
        return summary

    def _metabrasil_sweep(self, runs, commit, summary):
        """The loop itself; the caller owns the lock and the logging."""
        company = self.env.company
        api_model = self.env['metabrasil.api']
        currency = self._metabrasil_price_currency()
        tag = company.metabrasil_pod_tag_id
        for position, book in enumerate(self, start=1):
            isbn = book.barcode or book.default_code
            if not isbn:
                summary['skipped'] += 1
                # Carimba também aqui. O domínio do cron já não deixa passar
                # código vazio, mas este ramo é a última linha de defesa: um
                # livro que perca o ISBN depois de entrar no lote sairia daqui
                # sem data e voltaria em toda varredura seguinte -- o "morrer
                # no mesmo livro toda execução" que o lote existe para evitar.
                book.metabrasil_price_check_date = fields.Datetime.now()
                continue
            code, data = api_model.production_prices(company, str(isbn), runs)
            ladder = self._metabrasil_parse_ladder(data if code == 200 else {})
            # Stamped whatever the answer, so the next batch moves on to
            # books nobody has asked about instead of retrying these.
            book.metabrasil_price_check_date = fields.Datetime.now()
            if not ladder:
                # Two very different silences, and telling them apart is the
                # answer to "why did so few books come back": the printer
                # either does not have the title at all (400), or has it and
                # never priced it (200 with zeros). The first is a catalogue
                # upload; the second is a price to negotiate.
                if code == 200:
                    summary['no_price'] += 1
                else:
                    summary['unknown'] += 1
                # No price today. The books already priced keep their lines --
                # wiping them would leave purchase lines at zero, which is a
                # worse lie than a stale price -- but the tag comes off, so
                # the loss of coverage is visible and filterable.
                if tag and tag in book.product_tag_ids:
                    book.product_tag_ids = [fields.Command.unlink(tag.id)]
                summary['unpriced'] += 1
                continue
            book._metabrasil_store_ladder(ladder, currency)
            if tag and tag not in book.product_tag_ids:
                book.product_tag_ids = [fields.Command.link(tag.id)]
            summary['priced'] += 1
            if commit and not position % COMMIT_EVERY:
                self.env.cr.commit()
                _logger.info("Metabrasil price sweep: %s/%s books.",
                             position, len(self))
        return summary

    # ------------------------------------------------------------------
    # Concurrency: one sweep at a time
    # ------------------------------------------------------------------
    @api.model
    def _metabrasil_claim_sweep(self):
        """True if this process may sweep; False if one is already running.

        A stamped parameter rather than an in-memory flag, because the cron
        worker and the web worker are different processes. It self-heals: a
        worker killed mid-sweep leaves the stamp behind, and after
        LOCK_STALE_HOURS the next caller takes over rather than waiting for a
        human to clear it.
        """
        params = self.env['ir.config_parameter'].sudo()
        started = params.get_param(LOCK_PARAM)
        if started:
            try:
                age = fields.Datetime.now() - fields.Datetime.to_datetime(started)
                if age.total_seconds() < LOCK_STALE_MINUTES * 60:
                    _logger.info("Metabrasil price sweep already running "
                                 "since %s; skipping.", started)
                    return False
                _logger.warning("Metabrasil price sweep stamp from %s is "
                                "stale; taking over.", started)
            except (TypeError, ValueError):
                pass  # unreadable stamp: treat it as no lock at all
        params.set_param(LOCK_PARAM, fields.Datetime.to_string(
            fields.Datetime.now()))
        return True

    @api.model
    def _metabrasil_release_sweep(self):
        self.env['ir.config_parameter'].sudo().set_param(LOCK_PARAM, '')

    def action_metabrasil_refresh_prices(self):
        """List action: price the selected books, right now.

        Deliberately synchronous, because "run it on these five and show me"
        is the point -- but capped, because each book is a second of network
        and nobody should watch a browser spin through hundreds.
        """
        if len(self) > INLINE_LIMIT:
            raise UserError(_(
                "%(count)s books selected. Pricing them takes about "
                "%(minutes)s minute(s) of calls to the printer, too long to "
                "wait on this screen. Select %(limit)s or fewer, or use "
                "Settings > Metabrasil > Refresh Print Prices to sweep the "
                "whole catalogue in the background.",
                count=len(self), limit=INLINE_LIMIT,
                minutes=max(1, round(len(self) / 60))))
        summary = self._metabrasil_refresh_prices()
        return self._metabrasil_price_notification(summary)

    @api.model
    def _metabrasil_price_notification(self, summary):
        if summary.get('busy'):
            level, message = 'warning', _(
                "A price sweep is already running. Wait for it to finish "
                "rather than starting a second one -- two sweeps double the "
                "load on the printer's API and race each other.")
        elif summary['priced']:
            level, message = 'success', _(
                "%(priced)s book(s) priced. %(no_price)s the printer knows "
                "but has not priced, and %(unknown)s are not in your POD "
                "repository at all.", **summary)
        else:
            level, message = 'warning', _(
                "No price came back. %(no_price)s book(s) the printer knows "
                "but has not priced — that is a price to agree with them; "
                "%(unknown)s are not in your POD repository — those have to "
                "be uploaded there first.", **summary)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': level,
                       'title': _("Metabrasil print prices"),
                       'message': message,
                       'sticky': level != 'success'},
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _metabrasil_printable_domain(self):
        """Leave e-books out of the sweep, without depending on Metabooks.

        A printer prints paper. When the Metabooks catalogue is installed it
        carries the ONIX product form, where anything starting with 'E' is a
        digital edition -- asking the printer to quote those is a wasted call
        every fortnight.

        Deliberately a *soft* dependency: the field is looked up at runtime,
        so the module installs and runs with or without Metabooks. And the
        test excludes only what is *known* to be digital -- a book with no
        form recorded stays in, because absence of data is not evidence of an
        e-book.
        """
        if 'metabooks_product_form' not in self._fields:
            return []
        return ['|', ('metabooks_product_form', '=', False),
                     ('metabooks_product_form', 'not like', 'E%')]

    @api.model
    def _metabrasil_parse_ladder(self, data):
        """{'resultados': [{'tiragem': 100, 'valor': 527.2}]} -> {100: 5.272}.

        Two conversions happen here, both of them load-bearing:

        * **`valor` is the total for the whole print run, not the unit
          price.** Measured on live data: one title quotes 7.46 for a single
          copy and 527.20 for a hundred -- 5.27 each, a clean volume
          discount. `supplierinfo.price` is per unit, so storing their number
          raw would bill a 100-copy run at a hundred times its cost, quietly.
        * **A `valor` of zero is not a free book**, it is the printer saying
          it has no price for that title (401 of 417 quoted titles came back
          that way). Storing it would make purchase lines cost nothing, so a
          zero drops out and the book counts as unpriced.

        Keyed by `tiragem`, never by position: trusting the order would price
        a 100-copy run at the 50-copy rate the day they reorder the list.
        """
        ladder = {}
        for entry in (data.get('resultados') or []):
            try:
                run = int(entry['tiragem'])
                total = float(entry['valor'])
            except (KeyError, TypeError, ValueError):
                continue
            if run > 0 and total > 0:
                ladder[run] = total / run
        return ladder

    @api.model
    def _metabrasil_price_currency(self):
        """The printer quotes in BRL whatever the company's own currency is.

        Storing the number without saying so would read it as dollars on a
        USD company and understate the cost several times over, silently.
        """
        currency = self.env.ref('base.BRL', raise_if_not_found=False)
        if currency and not currency.active:
            currency.sudo().active = True
        return currency or self.env.company.currency_id

    def _metabrasil_store_ladder(self, ladder, currency):
        """Upsert one vendor-price line per print run, prune stale runs."""
        self.ensure_one()
        company = self.env.company
        printer = company.metabrasil_partner_id
        mine = self.seller_ids.filtered(
            lambda s: s.partner_id == printer
            and s.company_id in (False, company))
        for run, price in ladder.items():
            line = mine.filtered(lambda s: s.min_qty == run)[:1]
            if line:
                if (line.price, line.currency_id) != (price, currency):
                    line.write({'price': price, 'currency_id': currency.id})
            else:
                self.env['product.supplierinfo'].create({
                    'partner_id': printer.id,
                    'product_tmpl_id': self.id,
                    'min_qty': run,
                    'price': price,
                    'currency_id': currency.id,
                    'company_id': company.id,
                })
        # A run dropped from Settings must stop quoting, or the ladder keeps
        # answering with a tier nobody asks for any more.
        stale = mine.filtered(lambda s: s.min_qty not in ladder)
        if stale:
            stale.unlink()
        self.metabrasil_price_date = fields.Datetime.now()
