# -*- coding: utf-8 -*-
"""Garante o português desta tela, que o .po sozinho não entrega.

Medido no `dev` em 09/09/2026, e vale registrar porque custou tempo: as
entradas acrescentadas a um .po de módulo JÁ INSTALADO não são aplicadas. Nem
por `-u`, nem com `--i18n-overwrite`, nem com `--load-language=pt_BR`, nem por
`ir.module.module._update_translations(overwrite=True)`, nem chamando o
`TranslationImporter` do próprio Odoo sobre o arquivo. A referência existe no
`ir_model_data`, o `msgid` bate, o `msgfmt --check` passa -- e o rótulo segue
em inglês.

`update_field_translations` grava. É o que este hook usa.

O .po continua sendo a fonte de verdade e é o que vale numa instalação limpa;
este mapa é a garantia de que a tela está em português HOJE, nas bases que já
têm o módulo. O teste `test_nenhum_campo_nosso_fica_em_ingles` acusa se os dois
saírem de sincronia.
"""

# Rótulo em inglês (fonte) -> português. A chave é o nome do campo.
CAMPOS_PT_BR = {
    'print_flap_width': 'Largura da orelha (mm)',
    'print_cover_colors': 'Cor da capa',
    'print_body_colors': 'Cor do miolo',
    'print_body_extra_colors': 'Cadernos especiais',
    'print_cover_paper': 'Papel da capa',
    'print_cover_finish': 'Acabamento da capa',
    'print_body_paper': 'Papel do miolo',
    'print_notes': 'Observações gerais',
}

TERMOS_DA_VIEW = {
    'Cover': 'Capa',
    'Body': 'Miolo',
    'matte lamination with spot UV, gold foil on the spine...':
        'laminação fosca ou brilhante, com reserva, hotstamp...',
    '250gsm coated board': 'cartão triplex 250g',
    '80gsm bulky paper': 'pólen soft 80g',
    'insert, packaging, colour reference, deadline...':
        'encarte, embalagem, referência de cor, prazo...',
    '1 signature in 4x4, pages 65-80': '1 caderno 4x4, páginas 65-80',
}


def traduzir_a_tela(env):
    if not env['res.lang'].search([('code', '=', 'pt_BR')]):
        return

    campos = env['ir.model.fields'].search([
        ('model', 'in', ('product.template', 'product.product')),
        ('name', 'in', list(CAMPOS_PT_BR)),
    ])
    for campo in campos:
        campo.update_field_translations(
            'field_description', {'pt_BR': CAMPOS_PT_BR[campo.name]})

    vista = env.ref('liber_print_quote.view_product_template_print_finish',
                    raise_if_not_found=False)
    if vista:
        vista.update_field_translations('arch_db', {'pt_BR': TERMOS_DA_VIEW})
