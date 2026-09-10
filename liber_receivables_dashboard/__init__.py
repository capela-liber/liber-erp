# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """A primeira foto, no dia em que o módulo entra.

    Sem ela o gráfico de evolução nasce vazio e fica vazio até o dia 1 do
    mês seguinte -- um painel que abre em branco parece quebrado, não novo.
    """
    env['liber.receivables.snapshot']._tirar_foto()
