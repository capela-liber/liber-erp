# -*- coding: utf-8 -*-
"""Funde CFOPs repetidos antes de o código virar único.

O `pre_init_hook` cuida de quem instala pela primeira vez. Quem já tinha o
módulo não passa por ele -- e aí duas coisas quebram: a constraint de unicidade
não sobe (o Odoo avisa e segue, deixando o problema onde estava, agora em
silêncio) e os CFOPs que já existiam sem xmlid fazem o XML tentar recriá-los,
o que agora viola a unicidade e derruba o módulo inteiro.

Esta migração fecha os dois caminhos, chamando a mesma rotina do hook.
"""

import logging

from odoo.addons.liber_nfe_focus.hooks import preparar_cfops

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    from odoo.api import Environment
    from odoo import SUPERUSER_ID
    env = Environment(cr, SUPERUSER_ID, {})
    preparar_cfops(env)
