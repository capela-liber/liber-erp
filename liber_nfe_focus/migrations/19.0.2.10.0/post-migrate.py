# -*- coding: utf-8 -*-
"""Recolhe as cartas de correção que ficaram como anexo solto do painel.

Enquanto o `liber_nfe_xml` só tinha tabela de CANCELAMENTO, a emissão guardava
a CC-e como `ir.attachment` no registro do painel (`<chave>-carta-correcao.xml`)
— era o único lugar honesto disponível, já que gravá-la na tabela de
cancelamento marcaria a nota como cancelada. Agora existe tabela de eventos, e
a carta tem endereço próprio: este passo move as que ficaram para trás.

O anexo NÃO é apagado. Ele é a prova de origem do que se está convertendo, e o
espaço em jogo são alguns kilobytes.
"""
import base64
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    if 'nfe.xml.panel' not in env:
        return
    Panel = env['nfe.xml.panel'].sudo()
    if not hasattr(Panel, 'register_nfe_event'):
        _logger.warning("liber_nfe_focus: liber_nfe_xml ainda sem "
                        "register_nfe_event; cartas não convertidas.")
        return

    anexos = env['ir.attachment'].sudo().search([
        ('res_model', '=', 'nfe.xml.panel'),
        ('name', 'like', '%carta-correcao%'),
    ])
    convertidas = falhas = 0
    for anexo in anexos:
        if not anexo.datas:
            continue
        try:
            with cr.savepoint():
                evento = Panel.register_nfe_event(
                    base64.b64decode(anexo.datas),
                    file_name=anexo.name,
                    company_id=anexo.company_id.id or False)
            if evento:
                convertidas += 1
            else:
                falhas += 1
        except Exception:
            _logger.exception("liber_nfe_focus: carta %s não converteu", anexo.name)
            falhas += 1
    _logger.info("liber_nfe_focus: %s carta(s) de correção agora são eventos "
                 "(%s não converteram, anexos preservados).", convertidas, falhas)
