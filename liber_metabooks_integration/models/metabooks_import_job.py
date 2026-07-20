# -*- coding: utf-8 -*-
"""Background, resumable catalogue import.

A full publisher catalogue (hundreds of books + cover downloads) is far too slow
to import inside a single web request — Odoo kills the request at the worker time
limit (~120s). Instead the button/wizard creates a metabooks.import.job and a cron
processes it page by page, committing after every page. Progress is visible on the
job record and, if a batch is interrupted, the next cron run resumes from next_page.
"""
import datetime
import logging
import time

from odoo import _, api, fields, models

from ..services.metabooks_client import MetabooksError

_logger = logging.getLogger(__name__)

# keep each cron batch comfortably under the worker time limit
BATCH_DEADLINE_SECONDS = 90

# technical jobs cost one HTTP call per book, so commit in small chunks
TECHNICAL_BATCH_SIZE = 20

# a running job that has not committed for this long is presumed dead (worker
# killed, container restarted) and may be picked up again
STALE_JOB_SECONDS = 600


class MetabooksImportJob(models.Model):
    _name = "metabooks.import.job"
    _description = "Metabooks Catalogue Import"
    _order = "create_date desc"
    _rec_name = "mvb_id"

    mvb_id = fields.Char("Vendor / MVB ID", required=True)
    job_type = fields.Selection(
        [("catalog", "Catalogue import"),
         ("technical", "Technical sheet (one call per ISBN)")],
        default="catalog", required=True,
        help="The catalogue feed carries no dimensions, weight, page count, "
             "binding or NCM. A technical job tops those up on books already "
             "imported, one by-ISBN call each, without touching their price, "
             "name, category or cover.")
    with_covers = fields.Boolean("Download covers", default=True)
    with_technical = fields.Boolean(
        "Download technical sheets", default=False,
        help="After the catalogue feed finishes, also fetch each book's technical "
             "sheet (dimensions, weight, page count, binding, NCM) -- one by-ISBN "
             "call per book, queued as a follow-up job since it is far slower than "
             "the feed. Import by ISBN already carries the technical sheet, so this "
             "only applies to the publisher (catalogue) import.")
    limit = fields.Integer(
        "Limit", default=0, help="Stop after N products (0 = whole catalogue).")
    state = fields.Selection(
        [("queued", "Queued"), ("running", "Running"),
         ("done", "Done"), ("failed", "Failed")],
        default="queued", required=True, readonly=True)
    total = fields.Integer("Catalogue Size", readonly=True)
    imported = fields.Integer("Imported", readonly=True)
    total_pages = fields.Integer("Catalogue Pages", readonly=True)
    next_page = fields.Integer("Next Page", default=1, readonly=True)
    progress = fields.Float("Progress", compute="_compute_progress")
    message = fields.Text("Message", readonly=True)
    product_ids = fields.Many2many(
        "product.template", string="Imported Products", readonly=True)

    @api.depends("total", "imported")
    def _compute_progress(self):
        for job in self:
            job.progress = (100.0 * job.imported / job.total) if job.total else 0.0

    # ------------------------------------------------------------------ #
    #  Buttons                                                            #
    # ------------------------------------------------------------------ #
    def action_run_now(self):
        self._trigger_cron()
        return self.open_form_action()

    def action_refresh(self):
        """Reopen the record so the latest cron progress is shown."""
        return self.open_form_action()

    def action_requeue(self):
        self.write({"state": "queued", "next_page": 1, "imported": 0,
                    "message": False})
        self._trigger_cron()
        return True

    def action_view_products(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Imported Products"),
            "res_model": "product.template",
            "domain": [("id", "in", self.product_ids.ids)],
            "view_mode": "list,form",
            "target": "current",
        }

    def _trigger_cron(self):
        cron = self.env.ref(
            "liber_metabooks_integration.cron_metabooks_import_jobs",
            raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    @api.model
    def create_and_run(self, mvb_id, with_covers=True, limit=0, with_technical=False):
        job = self.create({
            "mvb_id": (mvb_id or "").strip(),
            "with_covers": with_covers,
            "limit": limit or 0,
            "with_technical": with_technical,
        })
        job._trigger_cron()
        return job

    def _queue_technical_followup(self):
        """After a catalogue import, top up the technical sheets the feed cannot
        carry -- a separate job, since it costs one by-ISBN call per book and is
        far slower than the feed. Reuses the same resumable technical machinery
        (_process_technical_batch / enrich_isbns), scoped to this vendor.

        Idempotent: if a technical job for this vendor is already queued or
        running, reuse it rather than stacking a second one (two would fight over
        the same rows)."""
        self.ensure_one()
        job = self.search([
            ("job_type", "=", "technical"), ("mvb_id", "=", self.mvb_id),
            ("state", "in", ("queued", "running"))], limit=1)
        if not job:
            job = self.create({"mvb_id": self.mvb_id, "job_type": "technical"})
            job._trigger_cron()
        return job

    def open_form_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Catalogue Import"),
            "res_model": "metabooks.import.job",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    # ------------------------------------------------------------------ #
    #  Processing                                                         #
    # ------------------------------------------------------------------ #
    @api.model
    def _cron_process_jobs(self):
        """Pick up queued jobs, and running jobs only once they look abandoned.

        A running job commits after every batch, so its write_date is a heartbeat.
        Without the staleness guard, a second cron run (or a shell run) grabs a job
        that is already being processed and the two workers fight over the same
        rows -- Postgres aborts one with "could not serialize access".
        """
        stale = fields.Datetime.now() - datetime.timedelta(
            seconds=STALE_JOB_SECONDS)
        jobs = self.search([
            "|",
            ("state", "=", "queued"),
            "&", ("state", "=", "running"), ("write_date", "<", stale),
        ])
        for job in jobs:
            if (job.mvb_id or "").strip() == "*":
                # Órfão do "Atualizar todas as fichas" (removido): com o branch
                # ALL_VENDORS fora, '*' viraria busca literal, zero produto, e o
                # job completaria "done" fingindo ter atualizado tudo. Melhor
                # falhar dizendo o porquê do que mentir que terminou.
                job.write({"state": "failed", "message":
                           "Job de 'todas as editoras' de uma versão antiga: "
                           "esta opção foi removida. Crie um job por editora."})
                continue
            job._process_batch()

    def _technical_domain(self):
        mvb = (self.mvb_id or "").strip()
        return [("metabooks_vendor_id", "=", mvb),
                ("default_code", "!=", False)]

    def _process_technical_batch(self, start):
        """Top up the technical sheet of already-imported books, ISBN by ISBN.

        Resumable: `imported` doubles as the offset into the (id-ordered) book
        list, so a cron hand-back or a crash restarts exactly where it stopped.
        """
        connector = self.env["metabooks.connector"]
        Product = self.env["product.template"]
        domain = self._technical_domain()
        self.total = Product.search_count(domain)
        while True:
            books = Product.search(
                domain, order="id", offset=self.imported, limit=TECHNICAL_BATCH_SIZE)
            if not books:
                self.state = "done"
                self.env.cr.commit()
                return
            res = connector.enrich_isbns(
                [b.default_code or b.barcode for b in books])
            self.imported += len(books)
            if res["not_found"]:
                _logger.info("Metabooks job %s: %s ISBN(s) not found on this batch",
                             self.id, len(res["not_found"]))
            if self.limit and self.imported >= self.limit:
                self.state = "done"
            self.env.cr.commit()
            if self.state == "done":
                return
            if time.monotonic() - start > BATCH_DEADLINE_SECONDS:
                self._trigger_cron()  # cron resumes from `imported`
                return

    def _process_batch(self):
        self.ensure_one()
        connector = self.env["metabooks.connector"]
        self.write({"state": "running"})
        self.env.cr.commit()
        start = time.monotonic()
        try:
            if self.job_type == "technical":
                self._process_technical_batch(start)
                return
            while True:
                res = connector.import_catalog_page(
                    self.mvb_id, self.next_page, self.with_covers)
                self.total_pages = res["total_pages"]
                self.total = res["total_elements"]
                self.imported += res["count"]
                if res["product_ids"]:
                    self.product_ids = [(4, pid) for pid in res["product_ids"]]

                reached_limit = self.limit and self.imported >= self.limit
                finished = (
                    res["count"] == 0
                    or res["total_pages"] == 0
                    or self.next_page >= res["total_pages"]
                    or reached_limit
                )
                self.next_page += 1
                if finished:
                    self.state = "done"
                self.env.cr.commit()  # persist progress after every page
                if finished:
                    # The feed carries no technical sheet: if asked, chain a
                    # follow-up job to top it up now that the books exist.
                    if self.with_technical:
                        self._queue_technical_followup()
                    break
                if time.monotonic() - start > BATCH_DEADLINE_SECONDS:
                    # hand back to the cron; it will resume from next_page
                    self._trigger_cron()
                    break
        except MetabooksError as exc:
            self.env.cr.rollback()
            self.write({"state": "failed", "message": str(exc)})
            self.env.cr.commit()
        except Exception as exc:  # noqa: BLE001 - record any failure for the user
            self.env.cr.rollback()
            _logger.exception("Metabooks import job %s failed", self.id)
            self.write({"state": "failed", "message": str(exc)})
            self.env.cr.commit()
