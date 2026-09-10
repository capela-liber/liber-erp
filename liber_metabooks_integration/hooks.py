# -*- coding: utf-8 -*-
"""Rótulos em português que o .po não entrega neste módulo.

Mesmo achado de 09/09/2026 registrado no liber_print_quote/hooks.py: entrada
acrescentada ao .po de um módulo já instalado não é aplicada por nenhum
caminho do carregador. `update_field_translations` grava. O .po continua como
fonte de verdade para instalação limpa; isto garante a tela hoje.
"""

CAMPOS_PT_BR = {
    'metabooks_export_last': 'Último envio à Metabooks',
    'metabooks_export_last_track': 'Corte do histórico',
    'metabooks_export_pending': 'Pendente de envio à Metabooks',
    'metabooks_export_pending_since': 'Pendente desde',
    'metabooks_thema_qualifier_ids': 'Qualificadores Thema',
    'metabooks_thema_id': 'Thema principal',
    'metabooks_thema_ids': 'Lista Thema',
    'metabooks_has_lamination': 'Capa laminada',
    'metabooks_has_emboss': 'Capa com relevo',
    'metabooks_has_foil_cover': 'Hotstamp na capa',
    'metabooks_has_foil_jacket': 'Hotstamp na sobrecapa',
    # "Corte decorado" era tradução literal do B419 e ninguém na produção
    # chama assim: na gráfica é FACA. O código ONIX segue o mesmo.
    'metabooks_has_decorated_edges': 'Faca',
    'metabooks_has_belly_band': 'Cinta',
}


def traduzir_os_rotulos(env):
    if not env['res.lang'].search([('code', '=', 'pt_BR')]):
        return
    campos = env['ir.model.fields'].search([
        ('model', 'in', ('product.template', 'product.product')),
        ('name', 'in', list(CAMPOS_PT_BR)),
    ])
    for campo in campos:
        campo.update_field_translations(
            'field_description', {'pt_BR': CAMPOS_PT_BR[campo.name]})
