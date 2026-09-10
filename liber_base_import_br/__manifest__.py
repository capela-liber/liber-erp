# -*- coding: utf-8 -*-
{
    'name': "Import in Brazilian format",
    'summary': "Spreadsheets with 59,90 and 05/03/2026 import as written",
    'description': """
Brazilian defaults for the import screen
========================================

The import client always sent the American separators - thousands "," and
decimal "." - hardcoded, whatever the language. Because the options arrived
filled in, the server's own auto-detector never ran, and a value with a single
separator fell back to them: **"59,90" was read as 5990.00**, a hundredfold,
with no error and nothing in the preview to warn anyone. Dates had the twin
problem: on an en_US session "05/03/2026" was guessed as 3 May.

This module flips the three defaults to Brazilian - decimal ",", thousands "."
and DD/MM/YYYY - by patching the public method that produces them. The options
stay editable: whoever is importing an American file just changes them back.
    """,
    'author': "Capela / Liber",
    'license': 'AGPL-3',
    'category': 'Technical',
    'version': '19.0.1.0.0',
    'depends': ['base_import'],
    'assets': {
        'web.assets_backend': [
            'liber_base_import_br/static/src/import_model_br.js',
        ],
    },
    'installable': True,
    'auto_install': True,
}
