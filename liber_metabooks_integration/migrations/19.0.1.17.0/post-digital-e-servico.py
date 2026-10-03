"""Ebook e abook passam a ser serviço, nunca estocáveis, faturados pelo pedido.

A regra nova (`_metabooks_digital_e_servico`) só age em quem é escrito; esta
passa nos que já estão lá. Idempotente.

O estoque que algum deles tenha (quant) fica onde está, só deixa de contar:
apagar movimento é decisão de quem cuida do estoque, não de uma migração.
"""
import logging

from odoo import api, SUPERUSER_ID

from odoo.addons.liber_metabooks_integration.services import onix_codes

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    digitais = env['product.template'].with_context(active_test=False).search([
        ('metabooks_product_type.name', 'in', onix_codes.DIGITAL_BOOK_TYPES),
        '|', '|', ('type', '!=', 'service'), ('is_storable', '=', True),
        ('invoice_policy', '!=', 'order'),
    ])
    digitais.with_context(metabooks_from_sync=True).write(
        {'type': 'service', 'is_storable': False, 'invoice_policy': 'order'})
    _logger.info("Metabooks: %s ebook/abook passaram a serviço", len(digitais))
