# -*- coding: utf-8 -*-
# `tools` primeiro: os modelos importam o registro, e o registro precisa estar
# populado antes que `capela.ai.tool.init()` tente espelhá-lo em banco.
from . import tools
from . import models
