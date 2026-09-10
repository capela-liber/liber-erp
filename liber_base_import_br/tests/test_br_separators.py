# -*- coding: utf-8 -*-
"""What the Brazilian import defaults are worth, measured on the server.

The module itself is a JS patch on the option defaults, which no Python test
can reach. What IS testable - and what actually matters - is the behaviour
those defaults buy: the same CSV imported with the core's American options
versus with ours. The first test pins the corruption (so we hear about it if
Odoo ever fixes it upstream); the rest pin the cure.
"""
from odoo.tests import TransactionCase, tagged

# One separator only, which is how a Brazilian price is normally written and
# exactly the case that falls through to the options instead of being inferred.
CSV_PRICES = "name,list_price\nLivro A,59,90\n"
# Quoted, so the comma inside the value survives the CSV split.
CSV_PRICES_QUOTED = 'name,list_price\nLivro A,"59,90"\nLivro B,"1.250,00"\n'

US_OPTIONS = {
    # 'has_headers', not 'headers' - the core reads the former
    "has_headers": True,
    "separator": ",",
    "quoting": '"',
    "float_thousand_separator": ",",
    "float_decimal_separator": ".",
}
BR_OPTIONS = dict(US_OPTIONS,
                  float_thousand_separator=".",
                  float_decimal_separator=",")


@tagged("post_install", "-at_install")
class TestBrSeparators(TransactionCase):
    def _import(self, csv, options):
        record = self.env["base_import.import"].create({
            "res_model": "product.template",
            # the field is documented as raw binary, NOT base64
            "file": csv.encode(),
            "file_type": "text/csv",
            "file_name": "precos.csv",
        })
        record.parse_preview(dict(options))
        result = record.execute_import(
            ["name", "list_price"], ["name", "list_price"], dict(options))
        self.assertFalse(result.get("messages"),
                         "import reported: %s" % result.get("messages"))
        return self.env["product.template"].browse(result["ids"])

    def test_american_options_corrupt_a_brazilian_price(self):
        """The bug, pinned: with the core defaults 59,90 becomes 5990.

        This is what every untouched import did - no error, nothing in the
        preview, a hundredfold on the price.
        """
        products = self._import(CSV_PRICES_QUOTED, US_OPTIONS)

        self.assertAlmostEqual(products[0].list_price, 5990.0, places=2)
        self.assertAlmostEqual(products[1].list_price, 1250.0, places=2,
                               msg="two separators are inferred by value, "
                                   "which is what makes the damage mixed")

    def test_brazilian_options_read_the_price_as_written(self):
        """With our defaults the same file imports the numbers it shows."""
        products = self._import(CSV_PRICES_QUOTED, BR_OPTIONS)

        self.assertAlmostEqual(products[0].list_price, 59.90, places=2)
        self.assertAlmostEqual(products[1].list_price, 1250.00, places=2)

    def test_thousands_dot_is_not_taken_for_a_decimal(self):
        """'1.250,00' must be 1250, never 1.25."""
        csv = 'name,list_price\nLivro C,"1.250,00"\n'
        products = self._import(csv, BR_OPTIONS)

        self.assertAlmostEqual(products.list_price, 1250.00, places=2)

    def test_a_plain_integer_still_works(self):
        """No separator at all is the boring case; it must stay boring."""
        products = self._import("name,list_price\nLivro D,42\n", BR_OPTIONS)

        self.assertAlmostEqual(products.list_price, 42.0, places=2)

    def test_ddmmyyyy_is_not_read_as_mmdd(self):
        """05/03/2026 is 5 March, and the format option says so outright."""
        options = dict(BR_OPTIONS, date_format="%d/%m/%Y")
        record = self.env["base_import.import"].create({
            "res_model": "product.template",
            "file": "name,activity_date_deadline\nLivro E,05/03/2026\n".encode(),
            "file_type": "text/csv",
            "file_name": "datas.csv",
        })
        preview = record.parse_preview(dict(options))

        self.assertNotIn("error", preview, preview.get("error", ""))
        # the preview echoes back the format actually in force
        self.assertEqual(preview["options"]["date_format"], "%d/%m/%Y")
