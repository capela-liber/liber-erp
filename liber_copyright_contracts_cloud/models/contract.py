# -*- coding: utf-8 -*-
import os
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _normal(name):
    """Comparable form of a file name: no accents, no case, no extension,
    no surrounding blanks. 'PEREIRA_Sermões.PDF' == 'pereira_sermoes'."""
    base, ext = os.path.splitext((name or "").strip())
    if ext.lower() not in (".pdf", ".docx", ".doc", ".odt"):
        base = (name or "").strip()
    text = unicodedata.normalize("NFKD", base)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


class EdlabContract(models.Model):
    _inherit = "edlab.contract"

    document_ids = fields.One2many(
        "edlab.contract.document", "contract_id", string="Documents")
    document_count = fields.Integer(compute="_compute_document_count")
    main_document_id = fields.Many2one(
        "edlab.contract.document", compute="_compute_main_document",
        string="Main document")
    # Ids, not a Many2many: a relation to liber.cloud.folder is read as the
    # user, and a contracts user without Cloud Files access could not even
    # open the contract (the tour showed it). A plain list feeds the picker's
    # domain and says nothing a reader could not already infer.
    allowed_cloud_folder_ids = fields.Json(
        compute="_compute_allowed_cloud_folders",
        help="Ids of the folders Settings chose for contract documents; the "
        "document picker's domain.")

    # The check before the Location goes away (09/10/2026): every file name
    # the Location lists must have become a linked document. While this is
    # not empty for some contract, the Location still holds information the
    # Documents tab does not.
    location_missing = fields.Char(
        string="Location without document",
        compute="_compute_location_missing", search="_search_location_missing",
        help="File names the Location lists that are not linked as a "
        "document yet. Empty means the Documents tab holds everything the "
        "Location says.")

    @api.depends("location", "document_ids.name")
    def _compute_location_missing(self):
        for contract in self:
            linked = {_normal(name) for name in contract.document_ids.mapped("name")}
            missing = [n.strip() for n in (contract.location or "").split(";")
                       if n.strip() and _normal(n) not in linked]
            contract.location_missing = "; ".join(missing) or False

    def _search_location_missing(self, operator, value):
        if operator not in ("=", "!=") or value is not False:
            raise UserError(_("Search this field only as set or not set."))
        contracts = self.search([("location", "!=", False)])
        with_missing = contracts.filtered("location_missing")
        return [("id", "in" if operator == "!=" else "not in", with_missing.ids)]

    @api.depends("document_ids")
    def _compute_document_count(self):
        for contract in self:
            contract.document_count = len(contract.document_ids)

    @api.depends("document_ids.is_main")
    def _compute_main_document(self):
        for contract in self:
            contract.main_document_id = contract.document_ids.filtered(
                "is_main")[:1]

    @api.depends("company_id")
    def _compute_allowed_cloud_folders(self):
        for contract in self:
            company = contract.company_id or self.env.company
            contract.allowed_cloud_folder_ids = (
                company._contract_cloud_folders().ids)

    def _edlab_ensure_main_document(self):
        """Exactly one main document while there are documents, and the
        Location follows it. The first linked one becomes main when none
        is marked; the Location is left alone when no document remains
        (it may be a paper archive reference)."""
        for contract in self:
            docs = contract.document_ids
            if not docs:
                continue
            main = docs.filtered("is_main")
            if not main:
                main = docs.sorted(lambda d: (d.sequence, d.id))[:1]
                main.with_context(edlab_no_main_sync=True).sudo().write(
                    {"is_main": True})
            name = main[:1].name
            listed = [_normal(n) for n in (contract.location or "").split(";")]
            if name and _normal(name) not in listed:
                contract.location = name

    def action_open_main_document(self):
        self.ensure_one()
        if not self.main_document_id:
            raise UserError(_("This contract has no document linked yet."))
        return self.main_document_id.action_open()

    def _edlab_contract_files(self):
        """Files of the configured folders, read as sudo for matching only:
        linking is a manager's act, opening still goes through the gate."""
        folders = self.env.company._contract_cloud_folders()
        if not folders:
            raise UserError(_(
                "Choose the folders that hold contract documents first "
                "(Settings > Copyright > Documents)."))
        return self.env["liber.cloud.file"].sudo().search(
            [("folder_id", "in", folders.ids)])

    def action_link_documents_by_name(self):
        """Match each contract's Location (a file name, as the spreadsheet
        import wrote them) against the files of the configured folders.

        Only an unambiguous match links: one file with that name. Two files
        with the same name in different folders are reported, never guessed.
        """
        files = self._edlab_contract_files()
        by_name = {}
        for file in files:
            by_name.setdefault(_normal(file.name), []).append(file)
        linked = ambiguous = missing = already = 0
        Document = self.env["edlab.contract.document"]
        for contract in self:
            # The spreadsheet writes several files in one Location, ';'-
            # separated: the contract first, then amendments, translations,
            # a termination. Each one is linked; the first becomes main
            # when the contract has none yet.
            names = [n for n in (contract.location or "").split(";") if n.strip()]
            original_location = contract.location
            for position, raw in enumerate(names):
                matches = by_name.get(_normal(raw), [])
                if len(matches) > 1:
                    ambiguous += 1
                    continue
                if not matches:
                    missing += 1
                    continue
                file = matches[0]
                if file in contract.document_ids.file_id:
                    already += 1
                    continue
                Document.create({
                    "contract_id": contract.id,
                    "file_id": file.id,
                    "is_main": position == 0 and not contract.document_ids,
                    "sequence": 10 + position,
                })
                linked += 1
            # A Location listing several files keeps listing them: it is the
            # paper trail of what was matched, and the main file is in it.
            if len(names) > 1 and contract.location != original_location:
                contract.location = original_location
        message = _(
            "%(linked)s file(s) linked, %(already)s already linked, "
            "%(missing)s name(s) without a matching file, %(ambiguous)s with "
            "several files of the same name.",
            linked=linked, already=already, missing=missing,
            ambiguous=ambiguous)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Contract documents"), "message": message,
                       "type": "success" if linked else "warning",
                       "sticky": bool(missing or ambiguous)},
        }
