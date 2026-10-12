# -*- coding: utf-8 -*-
"""A contract's document: a pointer to a file Cloud Files mirrors.

The file record sits behind its folder's read ACL, and Odoo 19 refuses to
read a many2one that points at a record the user cannot read -- the whole
contract form would fail for whoever lacks the folder. So the line keeps a
copy of what the list needs to show (name, provider, path), taken as sudo
when the file is chosen, and the gate is met only where it belongs: when
someone opens the document."""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

MIRRORED = ("name", "path", "provider")


class EdlabContractDocument(models.Model):
    _name = "edlab.contract.document"
    _description = "Copyright Contract Document"
    _order = "is_main desc, sequence, id"

    contract_id = fields.Many2one(
        "edlab.contract", required=True, index=True, ondelete="cascade")
    company_id = fields.Many2one(
        related="contract_id.company_id", store=True, index=True)
    sequence = fields.Integer(default=10)
    file_id = fields.Many2one(
        "liber.cloud.file", string="File", required=True, index=True,
        ondelete="cascade",
        help="The document, as Cloud Files mirrors it.")
    is_main = fields.Boolean(
        string="Main",
        help="The contract itself, as opposed to amendments and annexes. "
        "Its file name is the contract's Location.")
    name = fields.Char(readonly=True)
    path = fields.Char(readonly=True)
    provider = fields.Char(readonly=True)
    note = fields.Char(help="What this document is: amendment, renewal...")

    _contract_file_uniq = models.Constraint(
        "unique(contract_id, file_id)",
        "This file is already linked to the contract.")

    @api.model_create_multi
    def create(self, vals_list):
        # Demote BEFORE creating: the one-main constraint runs inside create.
        for vals in vals_list:
            if vals.get("is_main") and vals.get("contract_id"):
                current = self.search([("contract_id", "=", vals["contract_id"]),
                                       ("is_main", "=", True)])
                if current:
                    super(EdlabContractDocument, current).write({"is_main": False})
        documents = super().create(vals_list)
        documents._mirror_file()
        documents.contract_id._edlab_ensure_main_document()
        return documents

    def write(self, vals):
        if vals.get("is_main"):
            self._demote_other_mains()
        res = super().write(vals)
        if "file_id" in vals:
            self._mirror_file()
        if {"file_id", "is_main"} & set(vals):
            self.contract_id._edlab_ensure_main_document()
        return res

    def unlink(self):
        contracts = self.contract_id
        res = super().unlink()
        contracts.exists()._edlab_ensure_main_document()
        return res

    def _demote_other_mains(self):
        """Marking a document as main takes the mark from the previous one:
        switching is one click, not two in the right order."""
        for doc in self:
            others = doc.contract_id.document_ids.filtered(
                lambda d: d.is_main and d != doc)
            if others:
                super(EdlabContractDocument, others).write({"is_main": False})

    def _mirror_file(self):
        """Copy the file's name, path and provider label onto the line.
        Sudo: choosing the file already passed the picker's domain; the
        copy is what lets readers without the folder see the list."""
        for doc in self:
            file = doc.file_id.sudo()
            label = dict(file._fields["provider"]._description_selection(
                self.env)).get(file.provider, file.provider)
            super(EdlabContractDocument, doc).write({
                "name": file.name, "path": file.path, "provider": label})

    @api.constrains("is_main", "contract_id")
    def _check_one_main(self):
        for contract in self.contract_id:
            if len(contract.document_ids.filtered("is_main")) > 1:
                raise ValidationError(_(
                    "A contract has one main document; %s has more.",
                    contract.display_name))

    def action_open(self):
        """Open through Cloud Files: the folder's read ACL decides."""
        self.ensure_one()
        return self.file_id.action_download()
