# -*- coding: utf-8 -*-
"""ONIX 3.0 code lists we actually consume, transcribed from EDItEUR.

Only the subset the Metabooks feed emits for our catalogue is kept here; adding a
code is a one-line change. Sources (EDItEUR ONIX Codelists):
  * List 150 ProductForm            https://ns.editeur.org/onix/en/150
  * List 175 ProductFormDetail      https://ns.editeur.org/onix/en/175
  * List 64  PublishingStatus       https://ns.editeur.org/onix/en/64
  * List 21  EditionType            https://ns.editeur.org/onix/en/21

Labels are the Odoo *source* strings (English), translated in i18n/pt_BR.po like
the rest of the UI.
"""

# --- List 150: ProductForm. Physical shape of the product. ------------------
PRODUCT_FORM = [
    ("BA", "Book"),
    ("BB", "Hardback"),
    ("BC", "Paperback"),
    ("BD", "Loose-leaf"),
    ("BE", "Spiral bound"),
    ("BF", "Pamphlet"),
    ("BG", "Leather / fine binding"),
    ("BH", "Board book"),
    ("BI", "Rag book"),
    ("BJ", "Bath book"),
    ("BK", "Novelty book"),
    ("BL", "Slide bound"),
    ("BM", "Big book"),
    ("BN", "Part-work (fascicle)"),
    ("BO", "Fold-out book or chart"),
    ("BP", "Foam book"),
    ("BZ", "Other book format"),
    ("EA", "Digital (delivered electronically)"),
    ("EB", "Digital download and online"),
    ("EC", "Digital online / streamed"),
    ("ED", "Digital download"),
    ("AA", "Audio"),
    ("AC", "CD-Audio"),
    ("AI", "DVD Audio"),
    ("AJ", "Downloadable audio file"),
    ("AN", "Downloadable and online audio"),
    ("AO", "Online / streamed audio"),
    ("AZ", "Other audio format"),
    # sets and kits: a box of books is still a thing the warehouse ships
    ("SA", "Multiple-component retail product"),
    ("SB", "Multiple-component retail product, boxed"),
    ("SC", "Multiple-component retail product, slip-cased"),
    ("SD", "Multiple-component retail product, shrink-wrapped"),
    ("SE", "Multiple-component retail product, loose"),
    ("SF", "Multiple-component retail product, part(s) enclosed"),
    ("SG", "Multiple-component retail product, entirely digital"),
    ("VA", "Video"),
    ("VI", "DVD video"),
    ("XA", "Trade-only material"),
    ("ZA", "General merchandise"),
    ("ZE", "Game"),
    ("ZZ", "Other merchandise"),
]

# --- List 175: ProductFormDetail. -------------------------------------------
# The B3xx range is how the block is bound -- the single most load-bearing fact
# for a print quote (sewn signatures cost more than a glued spine and lie flat).
BINDING_BY_DETAIL = {
    "B301": "loose_leaf",
    "B302": "loose_leaf",
    "B303": "loose_leaf",
    "B304": "sewn",
    "B305": "adhesive",
    "B306": "library",
    "B307": "reinforced",
    "B308": "half",
    "B309": "quarter",
    "B310": "saddle",
}

BINDING = [
    ("sewn", "Sewn"),
    ("adhesive", "Unsewn / adhesive bound"),
    ("saddle", "Saddle-sewn"),
    ("library", "Library binding"),
    ("reinforced", "Reinforced binding"),
    ("half", "Half bound"),
    ("quarter", "Quarter bound"),
    ("loose_leaf", "Loose-leaf"),
]

# B5xx: finishing extras. Each one is a line item on a print order.
DETAIL_DUST_JACKET = ("B501", "B502", "B503")
DETAIL_FLAPS = "B504"
DETAIL_THUMB_INDEX = "B505"
DETAIL_RIBBON = "B506"

# E1xx: e-publication file formats.
EBOOK_FORMAT = {
    "E101": "EPUB",
    "E102": "OEB",
    "E103": "DOC",
    "E104": "DOCX",
    "E105": "HTML",
    "E106": "ODF",
    "E107": "PDF",
    "E108": "PDF/A",
    "E109": "RTF",
    "E112": "TXT",
    "E113": "XHTML",
    "E115": "XPS",
    "E116": "Amazon Kindle",
    "E127": "MOBI",
}

# --- List 64: PublishingStatus. Editorial life of the title, which is NOT the
# same thing as availability (list 65, already mapped): a title can be "Active"
# and still out of stock.
PUBLISHING_STATUS = [
    ("00", "Unspecified"),
    ("01", "Cancelled"),
    ("02", "Forthcoming"),
    ("03", "Postponed indefinitely"),
    ("04", "Active"),
    ("05", "No longer our product"),
    ("06", "Out of stock indefinitely"),
    ("07", "Out of print"),
    ("08", "Inactive"),
    ("09", "Unknown"),
    ("10", "Remaindered"),
    ("11", "Withdrawn from sale"),
    ("12", "Recalled"),
    ("13", "Active, but not sold separately"),
    ("16", "Temporarily withdrawn from sale"),
    ("17", "Permanently withdrawn from sale"),
]

# --- List 21: EditionType. --------------------------------------------------
EDITION_TYPE = {
    "ABR": "Abridged",
    "ADP": "Adapted",
    "ANN": "Annotated",
    "BLL": "Bilingual",
    "CRI": "Critical",
    "DGO": "Digital original",
    "ENL": "Enlarged",
    "FAC": "Facsimile",
    "FST": "Festschrift",
    "ILL": "Illustrated",
    "MDT": "Media tie-in",
    "NED": "New edition",
    "REV": "Revised",
    "SPE": "Special",
    "UBR": "Unabridged",
    "VAR": "Variorum",
}


def label(pairs, code):
    """Human label for a code in a selection-style list of pairs."""
    return dict(pairs).get(code) or code
