# -*- coding: utf-8 -*-
from . import models


def ligar_locais_de_armazenamento(env):
    """O que o core faz quando a caixinha é marcada, sem depender do clique.

    `res.config.settings.set_values` reativa o tipo "Transferência interna"
    (`int_type_id`) de cada armazém e desliga as duas views que escondem o
    botão Criar da lista e do formulário de locais -- mas só quando quem
    salva é administrador do Inventário, e só na transição desligado->ligado.
    Um módulo não tem clique nem transição, então repete os dois passos.

    Idempotente: rodar sobre um banco já ligado não muda nada. Devolve os
    armazéns cujo INT foi reativado, para o teste e para o log.
    """
    armazens = env['stock.warehouse'].with_context(active_test=False).search([])
    tipos = armazens.int_type_id.with_context(active_test=False)
    reativados = tipos.filtered(lambda t: not t.active)
    reativados.active = True
    for xmlid in ('stock.stock_location_view_tree2_editable',
                  'stock.stock_location_view_form_editable'):
        view = env.ref(xmlid, raise_if_not_found=False)
        if view and view.active:
            view.active = False
    return reativados.warehouse_id


def post_init_hook(env):
    ligar_locais_de_armazenamento(env)
