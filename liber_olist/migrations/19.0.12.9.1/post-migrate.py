# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """A caixa Marketplaces para as contas que já existem, e o espelho fresco.

    1. O 12.9.0 criava a caixa de despacho no primeiro pedido importado — e o
       depósito abriu o Inventário antes disso e não achou o cartão. As contas
       existentes ganham a caixa agora; as novas nascem com ela (create).

    2. Os crons de leitura ("ler pedidos" e "ler detalhe") eram diários — um
       espelho que passa o dia cego não serve a um filtro cujo espírito é
       CORRE. Viram 2 em 2 horas (decisão do dono, 18/08/2026), com a próxima
       rodada logo adiante. São noupdate no XML, daí o ajuste por aqui.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    for conta in env['olist.account'].search([]):
        conta._marketplace_picking_type()
    for xml_id in ('liber_olist.cron_olist_pull_orders',
                   'liber_olist.cron_olist_read_details'):
        cron = env.ref(xml_id, raise_if_not_found=False)
        if cron:
            cron.write({'interval_number': 2, 'interval_type': 'hours'})
            cr.execute(
                "UPDATE ir_cron SET nextcall = now() + interval '15 minutes' "
                "WHERE id = %s AND nextcall > now() + interval '2 hours'",
                (cron.id,))
