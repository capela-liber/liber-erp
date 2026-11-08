# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID
from odoo.tools.mail import is_html_empty

from odoo.addons.liber_soc_settlement.models.res_company import (
    MAP_EMAIL_SUBJECT_DEFAULT, MAP_EMAIL_TEXT_DEFAULT)


def migrate(cr, version):
    """Preenche com o padrão o assunto e o texto do e-mail do mapa mensal
    onde estão VAZIOS, para se editar a partir dele.

    Onde a coluna nasce nesta versão o default do campo já preenche; isto
    cobre o banco que pegou a 19.0.2.26.0, com os campos criados vazios.
    Texto já escrito por alguém não é tocado.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env['res.company'].search([]):
        valores = {}
        if not company.consignment_map_email_subject:
            valores['consignment_map_email_subject'] = MAP_EMAIL_SUBJECT_DEFAULT
        if is_html_empty(company.consignment_map_email_text):
            valores['consignment_map_email_text'] = MAP_EMAIL_TEXT_DEFAULT
        if valores:
            company.write(valores)
