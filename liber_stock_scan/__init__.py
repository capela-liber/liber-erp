# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    env['stock.location']._liber_etiquetar_prateleiras()
