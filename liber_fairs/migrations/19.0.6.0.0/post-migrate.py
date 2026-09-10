# -*- coding: utf-8 -*-
"""Feira marcada como RETORNADA com a mercadoria ainda na mesa.

Até esta versão, pedir o retorno gravava `returned` no mesmo clique -- e a
remessa de volta ficava esperando alguém embalar. Quem parou nesse meio do
caminho ficou com a ficha dizendo que o evento acabou e trinta e quatro
exemplares na praça, com o armazém trinta e quatro menor. Foi assim que o
defeito apareceu: "o estoque da loja não bate com o estoque na EV".

Aqui o estado volta a dizer a verdade. Quem tem remessa de volta pendente
volta para ENVIADO, e a chegada que nascera cedo demais (e que podia estar
reservando o exemplar parado no trânsito, aquele que nunca chegou na mesa) é
cancelada -- ela renasce sozinha, com o número certo, quando a remessa for
validada.

Feira que já concluiu a volta não é tocada.
"""


def migrate(cr, version):
    cr.execute("""
        SELECT DISTINCT f.id
          FROM event_fair f
          JOIN stock_picking p ON p.fair_id = f.id
         WHERE f.state = 'returned'
           AND p.fair_operation = 'return_dispatch'
           AND p.state NOT IN ('done', 'cancel')
    """)
    ids = [linha[0] for linha in cr.fetchall()]
    if not ids:
        return
    cr.execute("UPDATE event_fair SET state = 'shipped' WHERE id IN %s",
               (tuple(ids),))
    cr.execute("""
        SELECT id FROM stock_picking
         WHERE fair_id IN %s
           AND fair_operation = 'return'
           AND state NOT IN ('done', 'cancel')
    """, (tuple(ids),))
    chegadas = [linha[0] for linha in cr.fetchall()]
    print('liber_fairs: %s feira(s) voltaram para Enviado; %s chegada(s) de '
          'retorno a cancelar: %s' % (len(ids), len(chegadas), chegadas))
    if chegadas:
        # Pelo ORM, para o núcleo desfazer reserva e encadeamento.
        from odoo import api, SUPERUSER_ID
        env = api.Environment(cr, SUPERUSER_ID, {})
        env['stock.picking'].browse(chegadas).action_cancel()
