# -*- coding: utf-8 -*-
"""Odoo-facing layer over the pure MetabooksClient.

Responsibilities:
  * build a client from the saved credentials (and persist refreshed tokens);
  * map a Metabooks record (ONIX by-ISBN, or the lighter catalogue feed item)
    into product.template values;
  * keep imprints (selos) and collections (coleções) apart by filing every
    product under a product.category tree  Metabooks / <Selo> / <Coleção>;
  * upsert product.template records idempotently, keyed on the ISBN.
"""
import base64
import datetime
import logging
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services import onix_codes
from ..services.metabooks_client import (
    DEFAULT_BASE_URL,
    MetabooksClient,
    MetabooksError,
    clean_isbn,
)

_logger = logging.getLogger(__name__)

# ONIX code list 65 (product availability). Also used for the feed's
# availabilityStatePublisher, which follows the same scheme. Descriptions in pt-BR.
AVAILABILITY_LABELS = {
    "10": "Ainda não disponível",
    "11": "Aguardando estoque",
    "20": "Disponível",
    "21": "Em estoque",
    "22": "Sob encomenda",
    "23": "Impressão sob demanda",
    "30": "Temporariamente indisponível",
    "31": "Sem estoque",
    "32": "Em reimpressão",
    "33": "Aguardando reedição",
    "40": "Indisponível",
    "41": "Substituído por novo produto",
    "43": "Não mais fornecido",
    "45": "Cancelado",
    "46": "Retirado de venda",
    "47": "Saldo (remainder)",
    "48": "Substituído por impressão sob demanda",
    "51": "Esgotado (fora de catálogo)",
    "97": "Não mais estocado por nós",
    "98": "Sem informação / sem atualização recente",
    "99": "Consultar fornecedor",
}

# Fields written by _parse_technical(). Listed here so _upsert knows their False
# is a real value (no flaps, no dust jacket) rather than "no data".
TECHNICAL_KEYS = (
    "metabooks_height", "metabooks_width", "metabooks_thickness",
    "metabooks_weight", "metabooks_product_form", "metabooks_binding",
    "metabooks_form_detail", "metabooks_has_flaps", "metabooks_has_dust_jacket",
    "metabooks_has_thumb_index", "metabooks_has_ribbon", "metabooks_ebook_format",
    "metabooks_page_count", "metabooks_front_matter_pages",
    "metabooks_back_matter_pages", "metabooks_illustration_count",
    "metabooks_illustration_note", "metabooks_ncm", "metabooks_language",
    "metabooks_original_language", "metabooks_publishing_status",
    "metabooks_publication_city", "metabooks_publication_country",
    "metabooks_country_of_manufacture", "metabooks_edition_number",
    "metabooks_edition_type", "metabooks_publish_date", "metabooks_technical_sync",
)


class MetabooksConnector(models.AbstractModel):
    _name = "metabooks.connector"
    _description = "Metabooks API Connector"

    # ------------------------------------------------------------------ #
    #  Client                                                             #
    # ------------------------------------------------------------------ #
    def _get_client(self):
        icp = self.env["ir.config_parameter"].sudo()
        username = icp.get_param("metabooks_username")
        password = icp.get_param("metabooks_password")
        if not (username and password):
            raise UserError(_(
                "Set the Metabooks username and password in "
                "Settings → Metabooks first."))
        base_url = icp.get_param("metabooks_base_url") or DEFAULT_BASE_URL

        def _persist(token):
            icp.set_param("metabooks_authorisation_code", token)

        return MetabooksClient(
            username, password, base_url=base_url,
            token=icp.get_param("metabooks_authorisation_code"),
            on_token=_persist,
        )

    def test_connection(self):
        try:
            self._get_client().test_connection()
        except MetabooksError as exc:
            raise UserError(_("Metabooks connection failed:\n%s") % exc)
        return True

    # ------------------------------------------------------------------ #
    #  Public import entry points                                         #
    # ------------------------------------------------------------------ #
    def import_isbns(self, isbns):
        """Import/update products for a list of ISBNs.

        Idempotent: an existing book (matched on ISBN) is updated, never duplicated.
        Returns {'products': recordset, 'created': n, 'updated': n, 'not_found': [isbns]}.
        """
        client = self._get_client()
        Product = self.env["product.template"]
        products = Product
        created = updated = 0
        not_found = []
        for raw in isbns:
            isbn = clean_isbn(raw)
            if not isbn:
                continue
            try:
                data = client.get_product_by_isbn(isbn)
            except MetabooksError as exc:
                raise UserError(_("Metabooks error for ISBN %s:\n%s") % (isbn, exc))
            if not data:
                _logger.info("Metabooks: ISBN %s not found, skipped", isbn)
                not_found.append(isbn)
                continue
            existed = bool(Product.search(
                ["|", ("default_code", "=", isbn), ("barcode", "=", isbn)], limit=1))
            products |= self._upsert(self._parse_onix(data))
            if existed:
                updated += 1
            else:
                created += 1
        return {"products": products, "created": created,
                "updated": updated, "not_found": not_found}

    def import_publisher(self, mvb_id, limit=None, with_covers=True):
        """Import/update the whole catalogue of a publisher (VL / mvbId).

        Synchronous: fine for small/limited runs (e.g. the ISBN/test wizard).
        For a full catalogue use a metabooks.import.job (background, resumable),
        otherwise a big run will hit the HTTP worker time limit.
        """
        client = self._get_client()
        products = self.env["product.template"]
        for item in client.iter_publisher_products(mvb_id, limit=limit):
            parsed = self._parse_feed(item)
            parsed["_with_cover"] = with_covers
            products |= self._upsert(parsed)
        return products

    def import_catalog_page(self, mvb_id, page, with_covers=True):
        """Import a single catalogue page. Returns dict with paging metadata so a
        background job can iterate page by page and commit after each one."""
        client = self._get_client()
        data = client.catalog_page(mvb_id, page)
        if not data:
            return {"total_pages": 0, "total_elements": 0, "count": 0,
                    "product_ids": []}
        products = self.env["product.template"]
        for item in data.get("content", []):
            parsed = self._parse_feed(item)
            parsed["_with_cover"] = with_covers
            products |= self._upsert(parsed)
        return {
            "total_pages": data.get("totalPages", 1) or 1,
            "total_elements": data.get("totalElements", 0),
            "count": len(data.get("content", [])),
            "product_ids": products.ids,
        }

    # ------------------------------------------------------------------ #
    #  Categories: keep selos / coleções apart                            #
    # ------------------------------------------------------------------ #
    def _get_or_create_category(self, name, parent):
        Category = self.env["product.category"]
        name = (name or "").strip()
        if not name:
            return parent
        parent_id = parent.id if parent else False
        cat = Category.search(
            [("name", "=", name), ("parent_id", "=", parent_id)], limit=1)
        if not cat:
            cat = Category.create({"name": name, "parent_id": parent_id})
        return cat

    def _ensure_category(self, selo, collection=None):
        """Build/return the leaf category  <Selo> / <Coleção>  (collections nested
        inside their imprint). Returns an empty recordset if there is no imprint."""
        empty = self.env["product.category"]
        node = self._get_or_create_category(selo, empty)
        if not node:
            return empty
        if collection:
            node = self._get_or_create_category(collection, node) or node
        return node

    # ------------------------------------------------------------------ #
    #  Parsing helpers                                                    #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_date(value):
        """Metabooks is not consistent about date formats: the by-ISBN ONIX record
        uses 01.01.2010, the catalogue feed uses 01/01/2007, and ONIX dateformat
        fields use 20100101. Try each, longest-first, and never guess."""
        if not value:
            return False
        value = str(value).strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y",
                    "%d/%m/%Y", "%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.datetime.strptime(value[:len(fmt) + 2], fmt).date()
            except ValueError:
                continue
        # ONIX allows a year-only date (dateformat 05) when the publisher only
        # committed to a year; anchor it to January 1st rather than losing it.
        if len(value) == 4 and value.isdigit():
            return datetime.date(int(value), 1, 1)
        _logger.warning("Metabooks: unrecognised date format %r", value)
        return False

    @staticmethod
    def _to_int(value):
        """Page counts are not always arabic: front matter is classically numbered
        in roman numerals, and Metabooks passes that through verbatim ("XXIV")."""
        if not value:
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip()
        if text.isdigit():
            return int(text)
        roman = {"I": 1, "V": 5, "X": 10, "L": 50,
                 "C": 100, "D": 500, "M": 1000}
        upper = text.upper()
        if upper and all(ch in roman for ch in upper):
            total = 0
            for i, ch in enumerate(upper):
                val = roman[ch]
                nxt = roman.get(upper[i + 1]) if i + 1 < len(upper) else 0
                total += -val if val < nxt else val
            return total
        _logger.warning("Metabooks: unparseable page count %r", value)
        return 0

    def _ensure_country(self, code):
        if not code:
            return False
        country = self.env["res.country"].search(
            [("code", "=", str(code).strip().upper())], limit=1)
        return country.id or False

    # Metabooks product types that are DIGITAL: no box, no shelf, no stock.
    # Everything else (pbook, nonbook: games, calendars, posters) is a physical
    # object and must be storable.
    _DIGITAL_TYPES = ("ebook", "abook")

    @classmethod
    def _is_storable_type(cls, product_type):
        """A physical book must be storable, or it can never have stock.

        Odoo 19 defaults is_storable to False, and this connector never set it --
        so every title the catalogue created (and the NFe import had not already
        created) came in with NO stock tracking. It could never show On Hand, and
        therefore no campaign would ever place it: 114 of the 538 consignable
        titles were silently invisible to replenishment.
        """
        return bool(product_type) and str(product_type).strip().lower() \
            not in cls._DIGITAL_TYPES

    def _ensure_book_type(self, code):
        if not code:
            return False
        BookType = self.env["metabooks.book.type"]
        bt = BookType.search([("name", "=", code)], limit=1)
        if not bt:
            bt = BookType.create({"name": code})
        return bt.id

    def _ensure_availability(self, code):
        """Map a Metabooks availability code to a metabooks.avalaibility.definition."""
        if code in (None, "", False):
            return False
        code = str(code).strip()
        label = AVAILABILITY_LABELS.get(code, _("Code %s") % code)
        Avail = self.env["metabooks.avalaibility.definition"]
        rec = Avail.search([("identify_number", "=", code)], limit=1)
        if not rec:
            rec = Avail.create({"identify_number": code, "product_definition": label})
        elif not rec.product_definition:
            rec.product_definition = label
        return rec.id

    def _ensure_tags(self, names):
        """Find/create product.tag records for a list of subject/keyword names."""
        Tag = self.env["product.tag"]
        ids = []
        for name in names:
            name = (name or "").strip()
            if not name:
                continue
            tag = Tag.search([("name", "=ilike", name)], limit=1)
            if not tag:
                tag = Tag.create({"name": name})
            ids.append(tag.id)
        return ids

    @staticmethod
    def _compose_name(title, subtitle, authors):
        """Product name as the shelf knows the book: "Title: Subtitle (Contributors)".

        Contributors are part of the name on purpose: staff usually recall the
        author before the title, and the name is what every Odoo search box, order
        line and picking list shows.

        Publishers sometimes type the colon into the ONIX title field itself
        ("Um brinde aos mortos:"), which is why the separator is rebuilt rather
        than trusted.
        """
        title = (title or "").strip().rstrip(":;, ")
        subtitle = (subtitle or "").strip().lstrip(":;, ")
        name = "%s: %s" % (title, subtitle) if subtitle else title
        authors = [a for a in (authors or []) if a]
        if authors:
            name = "%s (%s)" % (name, "; ".join(authors))
        return name

    @staticmethod
    def _contributor_name(contrib):
        """Display name of one ONIX contributor: a person, or a corporate body."""
        first = (contrib.get("firstName") or "").strip()
        last = (contrib.get("lastName") or "").strip()
        person = " ".join(p for p in (first, last) if p)
        return person or (contrib.get("groupName") or "").strip()

    def _ensure_author(self, first, last, role_code, bio, sequence=0):
        first = (first or "").strip()
        last = (last or "").strip()
        if not (first or last):
            return None
        Author = self.env["metabooks.auther.publiser"]
        author = Author.search(
            [("name", "=", first), ("author_last_name", "=", last)], limit=1)
        vals = {"name": first, "author_last_name": last, "is_auther": True}
        if bio:
            vals["auhor_biographical_note"] = bio
        if sequence:
            vals["author_sequence_number"] = sequence
        if role_code:
            role = self.env["author.contributor.role"].search(
                [("name", "=", role_code)], limit=1)
            # The role lives on the contributor, not on the book/contributor pair,
            # so the same person cannot be author here and translator there. Keep
            # the first role seen rather than letting the last import win.
            if role and not (author and author.author_contributor_role):
                vals["author_contributor_role"] = role.id
        if author:
            author.write(vals)
        else:
            author = Author.create(vals)
        return author.id

    def _ensure_contributors(self, contributors):
        """Contributor records + display names, in the order ONIX declares them."""
        ordered = sorted(contributors or [],
                         key=lambda c: c.get("sequenceNumber") or 99)
        ids, names = [], []
        for c in ordered:
            first = c.get("firstName")
            last = c.get("lastName")
            # a corporate contributor (a collective, an institution) has no
            # first/last name, only a group name
            if not (first or last) and c.get("groupName"):
                last = c["groupName"]
            aid = self._ensure_author(
                first, last,
                c.get("contributorRole") or c.get("type"),
                c.get("biographicalNote"),
                sequence=c.get("sequenceNumber") or 0)
            if aid:
                ids.append(aid)
            display = self._contributor_name(c)
            if display:
                names.append(display)
        return ids, names

    def _download_cover(self, url):
        if not url:
            return False
        # Metabooks cover URLs (api.metabooks.com/.../cover/<isbn>/m) require the
        # bearer token passed as an access_token query parameter, else they 401.
        token = self.env["ir.config_parameter"].sudo().get_param(
            "metabooks_authorisation_code")
        if token and "access_token=" not in url:
            url = "%s%saccess_token=%s" % (url, "&" if "?" in url else "?", token)
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200 and resp.content:
                return base64.b64encode(resp.content)
            _logger.warning("Metabooks: cover HTTP %s for %s", resp.status_code, url)
        except requests.RequestException:
            _logger.warning("Metabooks: cover download failed for %s", url)
        return False

    # ------------------------------------------------------------------ #
    #  Technical sheet: the physical spec a printer quotes from            #
    # ------------------------------------------------------------------ #
    def _parse_technical(self, data):
        """Physical/ONIX specification of a book, from the by-ISBN record.

        Split out from _parse_onix because it is also written on its own, by
        enrich_isbns(), over books whose editorial and commercial fields must not
        be touched. The catalogue feed carries none of this.
        """
        form = data.get("form") or {}
        extent = data.get("extent") or {}
        edition = data.get("edition") or {}

        details = form.get("productFormDetail") or []
        if isinstance(details, str):
            details = [details]
        details = [str(d).strip().upper() for d in details if d]

        binding = next(
            (onix_codes.BINDING_BY_DETAIL[d] for d in details
             if d in onix_codes.BINDING_BY_DETAIL), False)
        ebook_format = ", ".join(
            onix_codes.EBOOK_FORMAT[d] for d in details
            if d in onix_codes.EBOOK_FORMAT) or False

        ncm = next(
            (c.get("productClassificationCode")
             for c in data.get("productClassifications") or []
             if c.get("productClassificationType") == "10"), False)

        languages = data.get("languages") or []
        language = next((l.get("languageCode") for l in languages
                         if l.get("languageRole") == "01"), False)
        original_language = next((l.get("languageCode") for l in languages
                                  if l.get("languageRole") == "02"), False)

        # Metabooks fills mainContentPageCount (the block); contentPageCount is
        # the rare fallback. Reading only the latter is why page counts were 0.
        pages = self._to_int(
            extent.get("mainContentPageCount") or extent.get("contentPageCount"))

        ed_types = edition.get("editionType") or []
        if isinstance(ed_types, str):
            ed_types = [ed_types]
        ed_label = ", ".join(
            onix_codes.EDITION_TYPE.get(t, t) for t in ed_types) or False

        city = data.get("publicationCity") or []
        if isinstance(city, str):
            city = [city]

        status = data.get("publishingStatus")
        valid_status = dict(onix_codes.PUBLISHING_STATUS)
        if status and status not in valid_status:
            _logger.warning("Metabooks: unknown publishing status %r", status)
            status = False

        product_form = form.get("productForm")
        if product_form and product_form not in dict(onix_codes.PRODUCT_FORM):
            _logger.warning("Metabooks: unknown product form %r", product_form)
            product_form = False

        return {
            # dimensions are millimetres, weight is grams
            "metabooks_height": form.get("height") or 0.0,
            "metabooks_width": form.get("width") or 0.0,
            "metabooks_thickness": form.get("thickness") or 0.0,
            "metabooks_weight": form.get("weight") or 0.0,
            "metabooks_product_form": product_form,
            "metabooks_binding": binding,
            "metabooks_form_detail": ", ".join(details) or False,
            "metabooks_has_flaps": onix_codes.DETAIL_FLAPS in details,
            "metabooks_has_dust_jacket": any(
                d in details for d in onix_codes.DETAIL_DUST_JACKET),
            "metabooks_has_thumb_index": onix_codes.DETAIL_THUMB_INDEX in details,
            "metabooks_has_ribbon": onix_codes.DETAIL_RIBBON in details,
            "metabooks_ebook_format": ebook_format,
            "metabooks_page_count": pages,
            "metabooks_front_matter_pages": self._to_int(
                extent.get("frontMatterPageCount")),
            "metabooks_back_matter_pages": self._to_int(
                extent.get("backMatterPageCount")),
            "metabooks_illustration_count": self._to_int(
                extent.get("numberOfIllustrations")),
            "metabooks_illustration_note": extent.get("illustrationNote") or False,
            "metabooks_ncm": ncm,
            "metabooks_language": language,
            "metabooks_original_language": original_language,
            "metabooks_publishing_status": status,
            "metabooks_publication_city": city[0] if city else False,
            "metabooks_publication_country": self._ensure_country(
                data.get("publicationCountry")),
            "metabooks_country_of_manufacture": self._ensure_country(
                data.get("countryOfManufacture")),
            "metabooks_edition_number": self._to_int(edition.get("editionNumber")),
            "metabooks_edition_type": ed_label,
            "metabooks_publish_date": self._parse_date(data.get("publicationDate")),
            "metabooks_technical_sync": fields.Datetime.now(),
        }

    def enrich_isbns(self, isbns):
        """Write only the technical sheet onto books that already exist.

        The catalogue feed cannot carry dimensions, weight, page count, binding or
        NCM, so a feed-imported book has to be topped up with one by-ISBN call each.
        Editorial/commercial fields (name, price, category, cover) are deliberately
        left as they are in Odoo.
        """
        client = self._get_client()
        Product = self.env["product.template"]
        updated = 0
        not_found = []
        for raw in isbns:
            isbn = clean_isbn(raw)
            if not isbn:
                continue
            product = Product.search(
                ["|", ("default_code", "=", isbn), ("barcode", "=", isbn)], limit=1)
            if not product:
                not_found.append(isbn)
                continue
            data = client.get_product_by_isbn(isbn)
            if not data:
                _logger.info("Metabooks: ISBN %s not found, skipped", isbn)
                not_found.append(isbn)
                continue
            product.write(self._parse_technical(data))
            updated += 1
        return {"updated": updated, "not_found": not_found}

    def recompose_names(self, isbns):
        """Rewrite name, title, subtitle and contributor list from the ONIX record.

        Books imported through the catalogue feed carry only the main title and no
        contributors at all, so both the name and the author list have to be built
        from the by-ISBN record. Price, category and cover are left alone.
        """
        client = self._get_client()
        Product = self.env["product.template"]
        updated = 0
        not_found = []
        for raw in isbns:
            isbn = clean_isbn(raw)
            if not isbn:
                continue
            product = Product.search(
                ["|", ("default_code", "=", isbn), ("barcode", "=", isbn)], limit=1)
            if not product:
                not_found.append(isbn)
                continue
            data = client.get_product_by_isbn(isbn)
            if not data:
                not_found.append(isbn)
                continue
            parsed = self._parse_onix(data)
            vals = parsed["vals"]
            write_vals = {
                "name": vals["name"],
                "metabooks_book_title": vals["metabooks_book_title"],
                "metabooks_book_subtitle": vals["metabooks_book_subtitle"],
            }
            if vals.get("book_auther_ids"):
                write_vals["book_auther_ids"] = vals["book_auther_ids"]
            product.write(write_vals)
            updated += 1
        return {"updated": updated, "not_found": not_found}

    # ------------------------------------------------------------------ #
    #  ONIX (get_product_by_isbn) -> vals                                 #
    # ------------------------------------------------------------------ #
    def _parse_onix(self, data):
        pub = data.get("publisherData") or {}
        edition = data.get("edition") or {}

        # ISBN-13 (identifier types 03 / 15)
        isbn = ""
        for ident in data.get("identifiers", []):
            if ident.get("productIdentifierType") in ("03", "15"):
                isbn = clean_isbn(ident.get("idValue"))
                break

        # title (+ subtitle from titles or explicit)
        titles = data.get("titles") or [{}]
        title = titles[0].get("title") or isbn

        # price: prefer recommended retail (type 02), else first
        price = 0.0
        prices = data.get("prices") or []
        chosen = next((p for p in prices if p.get("priceType") == "02"), None) or (
            prices[0] if prices else None)
        if chosen:
            price = chosen.get("priceAmount") or 0.0

        # synopsis: textContents type 03 (description)
        synopsis = ""
        for tc in data.get("textContents", []):
            if tc.get("textType") == "03" and tc.get("text"):
                synopsis = tc["text"]
                break

        # cover: supportingResources with content type 01 (front cover)
        cover_url = False
        for res in data.get("supportingResources", []):
            if res.get("resourceContentType") == "01" and res.get("exportedLink"):
                cover_url = res["exportedLink"]
                break

        authors, author_names = self._ensure_contributors(data.get("contributors"))

        # keywords: subjects with scheme 20 (Keywords) carry the free-text terms
        keywords = [
            s.get("subjectHeadingText") for s in data.get("subjects", [])
            if s.get("subjectSchemeIdentifier") == "20" and s.get("subjectHeadingText")
        ]

        subtitle = titles[0].get("subtitle") or ""
        selo = pub.get("shortName") or pub.get("name")
        vals = {
            "name": self._compose_name(title, subtitle, author_names),
            "default_code": isbn,
            "barcode": isbn or False,
            "list_price": price,
            "metabooks_book_title": title,
            "metabooks_book_subtitle": subtitle,
            "synopsys": synopsis,
            "metabooks_publisher": pub.get("name"),
            "metabooks_label": selo,
            "metabooks_vendor_id": pub.get("mvbId"),
            "metabooks_keywords": ", ".join(keywords),
            "metabooks_product_availability": self._ensure_availability(
                data.get("productAvailability")),
            "metabooks_creation_date": self._parse_date(data.get("creationDate")),
            "metabooks_last_updatedate": self._parse_date(data.get("lastModificationDate")),
            "edition": edition.get("editionStatement") or (
                str(edition.get("editionNumber")) if edition.get("editionNumber") else False),
            "metabooks_product_type": self._ensure_book_type(data.get("productType")),
            "type": "consu",
            "is_storable": self._is_storable_type(data.get("productType")),
            "book_auther_ids": [(6, 0, authors)] if authors else False,
        }
        # dimensions, weight, pages, binding, NCM, languages, publishing status
        vals.update(self._parse_technical(data))
        return {
            "isbn": isbn,
            "vals": vals,
            "selo": selo,
            "collection": None,  # ONIX by-ISBN carries no collection
            "cover_url": cover_url,
            "tags": keywords,
            "_with_cover": True,
        }

    # ------------------------------------------------------------------ #
    #  Catalogue feed item -> vals                                        #
    # ------------------------------------------------------------------ #
    def _parse_feed(self, item):
        isbn = clean_isbn(item.get("isbn") or item.get("identifier") or item.get("gtin"))
        title = item.get("title") or isbn
        collections = item.get("collections") or []
        collection = collections[0].get("title") if collections else None
        selo = item.get("publisher")

        # feed keyWords may be a string OR a list (or empty). Full keywords live in
        # the by-ISBN detail. availabilityStatePublisher follows the same ONIX scheme.
        raw_kw = item.get("keyWords") or []
        if isinstance(raw_kw, str):
            raw_kw = re.split(r"[;,]", raw_kw)
        keywords = [str(k).strip() for k in raw_kw if str(k).strip()]

        # The feed carries contributors too (role in `type`), but the old parser
        # ignored them: that is why every feed-imported book had an empty author
        # list. Fall back to the flat `author` string when the list is absent.
        authors, author_names = self._ensure_contributors(item.get("contributors"))
        if not author_names and item.get("author"):
            author_names = [item["author"].strip()]

        subtitle = item.get("subTitle") or ""
        vals = {
            "name": self._compose_name(title, subtitle, author_names),
            "default_code": isbn,
            "barcode": isbn or False,
            "list_price": item.get("priceBrl") or 0.0,
            "metabooks_book_title": title,
            "metabooks_book_subtitle": subtitle,
            "synopsys": item.get("mainDescription") or item.get("shortDescription") or "",
            "metabooks_publisher": selo,
            "metabooks_label": selo,
            "metabooks_vendor_id": item.get("publisherMbId"),
            "metabooks_collections": collection or "",
            "metabooks_keywords": ", ".join(keywords),
            "metabooks_product_availability": self._ensure_availability(
                item.get("availabilityStatePublisher") or item.get("availabilityStateFeed")),
            "metabooks_publish_date": self._parse_date(item.get("publicationDate")),
            "metabooks_last_updatedate": self._parse_date(item.get("lastModifiedDate")),
            "edition": str(item.get("edition")) if item.get("edition") else False,
            "metabooks_product_type": self._ensure_book_type(item.get("productType")),
            "type": "consu",
            "is_storable": self._is_storable_type(item.get("productType")),
            "book_auther_ids": [(6, 0, authors)] if authors else False,
        }
        return {
            "isbn": isbn,
            "vals": vals,
            "selo": selo,
            "collection": collection,
            "cover_url": item.get("coverUrl"),
            "tags": keywords,
            "_with_cover": True,
        }

    # ------------------------------------------------------------------ #
    #  Upsert                                                             #
    # ------------------------------------------------------------------ #
    def _upsert(self, parsed):
        # Writes here carry Metabooks' own data back into Odoo. Without this
        # flag every import would mark the book as pending export and queue it
        # to be sent straight back to them -- see product.template.write in
        # metabooks_export.py.
        Product = self.env["product.template"].with_context(
            metabooks_from_sync=True)
        isbn = parsed["isbn"]
        vals = dict(parsed["vals"])
        # Drop falsy m2m/relational placeholders we set to False, but keep the
        # keys whose False is meaningful -- a book that lost its flaps, or whose
        # publish date was cleared upstream, must be cleared here too.
        keep_false = {
            "barcode", "metabooks_publish_date", "metabooks_creation_date",
            "metabooks_last_updatedate", "metabooks_product_type", "edition",
        } | set(TECHNICAL_KEYS)
        vals = {k: v for k, v in vals.items() if v is not False or k in keep_false}

        category = self._ensure_category(
            parsed.get("selo"), parsed.get("collection"))
        if category:
            vals["categ_id"] = category.id

        product = False
        if isbn:
            product = Product.search(
                ["|", ("default_code", "=", isbn), ("barcode", "=", isbn)], limit=1)
        if product:
            product.write(vals)
        else:
            product = Product.create(vals)

        # subjects/keywords -> product tags (add without wiping manual tags)
        tag_ids = self._ensure_tags(parsed.get("tags") or [])
        if tag_ids:
            product.product_tag_ids = [(4, tid) for tid in tag_ids]

        if parsed.get("_with_cover") and parsed.get("cover_url"):
            image = self._download_cover(parsed["cover_url"])
            if image:
                product.image_1920 = image
        return product
