# -*- coding: utf-8 -*-

from . import models
from . import wizard
from . import report
from . import controller

from .models.nfe_cfop import classify_cfops


def post_init_hook(env):
    """The CFOP decides the document -- and that is a rule, not a setting.

    It cannot live in a data file. The CFOPs are already seeded with noupdate, so a
    record carrying the same external id would never be written, and one carrying a
    new id would duplicate the CFOP (it happened: two 5113). The classification is
    therefore matched by CODE -- which is the only thing that identifies a CFOP
    anyway -- and re-applied on every upgrade: if the rule changes in the code, it
    changes in the database.
    """
    classify_cfops(env)
