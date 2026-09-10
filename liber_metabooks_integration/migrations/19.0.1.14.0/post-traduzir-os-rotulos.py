"""Hook de instalação não roda no `-u`; esta migração roda. Idempotente."""
from odoo import api, SUPERUSER_ID

from odoo.addons.liber_metabooks_integration.hooks import traduzir_os_rotulos


def migrate(cr, version):
    traduzir_os_rotulos(api.Environment(cr, SUPERUSER_ID, {}))
