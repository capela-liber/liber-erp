"""Hook de instalação não roda no `-u`; esta migração roda. Idempotente."""
from odoo import api, SUPERUSER_ID

from odoo.addons.liber_print_quote.hooks import traduzir_a_tela


def migrate(cr, version):
    traduzir_a_tela(api.Environment(cr, SUPERUSER_ID, {}))
