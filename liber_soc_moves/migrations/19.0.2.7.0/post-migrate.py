# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Take the COM/MOV shelf flow off the Inventory Overview.

    O tipo agora nasce arquivado (ver res_company), mas as bases que já
    passaram por uma remessa carregam um ativo -- e é exatamente o cartão
    "Remessa de Consignação" que ele achou confuso ao lado de "Entrega de
    Consignação": o nome dizia remessa, o conteúdo era o movimento interno de
    prateleira, e a fila estava vazia porque ninguém consegue mais criar uma.

    Arquivar aqui não encosta em uma transferência sequer: as COM/MOV/ (e as
    COM/ das bases anteriores ao padrão direcional) guardam nome, numeração e
    estado. É o mesmo caminho do ACERTO em 19.0.2.8.0 do soc_settlement.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    operation_types = env['res.company'].search([]).mapped(
        'consignment_shipment_operation_type_id')
    operation_types.filtered('active').active = False
