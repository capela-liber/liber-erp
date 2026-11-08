# -*- coding: utf-8 -*-
"""Os Dinheiros que os caixas de feira já tinham entram para a reserva.

Antes das gavetas, o PDV dava a cada empresa UM Dinheiro, no primeiro caixa,
num diário chamado "Cash". Ele vira a gaveta 01 da empresa; se o caixa que o
segura já está arquivado, a gaveta volta livre para a próxima feira.

Só se adota a forma de dinheiro que NENHUM caixa fora de feira usa: a gaveta
da loja não é da feira.
"""
from odoo import SUPERUSER_ID, Command, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    # A feira apagada solta o caixa (`fair_id` vazio), mas a operação dele
    # continua marcada como caixa de feira.
    caixas = env['pos.config'].search([
        '|', ('fair_id', '!=', False),
        ('picking_type_id.is_fair_register', '=', True)])
    outros = env['pos.config'].search([('id', 'not in', caixas.ids)])
    metodos = caixas.payment_method_ids.filtered('is_cash_count') \
        - outros.payment_method_ids
    for empresa in metodos.company_id:
        for n, metodo in enumerate(metodos.filtered(
                lambda m: m.company_id == empresa).sorted('id'), start=1):
            metodo.fair_drawer = True
            diario = metodo.journal_id
            diario.with_context(lang='en_US').name = 'Fair cash %02d' % n
            diario.with_context(lang='pt_BR').name = \
                'Dinheiro de feira %02d' % n
            diario.show_on_dashboard = False
            print('gaveta %s: %s' % (empresa.name, diario.code))
    for caixa in caixas.filtered(lambda c: not c.active):
        gavetas = caixa.payment_method_ids.filtered('fair_drawer')
        if gavetas:
            caixa.with_context(active_test=True).payment_method_ids = [
                Command.unlink(g.id) for g in gavetas]
            print('gaveta devolvida pelo caixa arquivado %s' % caixa.name)
