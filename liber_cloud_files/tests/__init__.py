# -*- coding: utf-8 -*-
# `common` is deliberately NOT imported here: it holds the shared gate
# suite, which each provider module runs against its own shelf. Importing
# it would make the chassis run it once with no provider at all.
