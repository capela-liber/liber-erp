# -*- coding: utf-8 -*-
"""O operador virou contato: converte o que foi digitado à mão.

O campo passou de texto livre para `res.partner`, e um campo obrigatório não
aceita linha antiga em branco. Aqui cada nome digitado vira (ou reencontra) um
contato com o mesmo nome. Criar contato é menos destrutivo do que apagar a
linha: quem operou a feira operou, e o registro disso não se joga fora.

Contato se cria pelo ORM, e não por INSERT: `res_partner` tem colunas NOT NULL
que vêm de outros módulos (autopost_bills, entre outras), e um INSERT cru
quebra no primeiro banco que tenha um módulo a mais.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    cr.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='event_fair_cashier'""")
    colunas = {linha[0] for linha in cr.fetchall()}
    if 'name' not in colunas:
        return
    if 'partner_id' not in colunas:
        cr.execute(
            "ALTER TABLE event_fair_cashier ADD COLUMN partner_id integer")
    cr.execute("""SELECT id, name FROM event_fair_cashier
                   WHERE partner_id IS NULL
                     AND name IS NOT NULL AND name <> ''""")
    pendentes = cr.fetchall()
    if pendentes:
        env = api.Environment(cr, SUPERUSER_ID, {})
        for cashier_id, nome in pendentes:
            contato = env['res.partner'].search(
                [('name', '=', nome)], limit=1)
            if not contato:
                contato = env['res.partner'].create({'name': nome})
            cr.execute(
                "UPDATE event_fair_cashier SET partner_id = %s WHERE id = %s",
                (contato.id, cashier_id))
    # linha sem nome nenhum não tem como virar contato: some
    cr.execute("DELETE FROM event_fair_cashier WHERE partner_id IS NULL")
