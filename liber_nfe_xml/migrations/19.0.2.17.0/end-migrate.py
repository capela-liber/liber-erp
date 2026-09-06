# -*- coding: utf-8 -*-
"""Derruba o que o upgrade deixa para trás da varredura SEFAZ DFe.

O ``_process_end`` apaga o modelo e os campos, mas deixa a tabela do modelo
removido e a tabela da relação com as notas. Aqui, depois de tudo carregado,
elas vão embora — estavam vazias em todos os bancos.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("DROP TABLE IF EXISTS nfe_sefaz_sweep_panel_rel")
    cr.execute("DROP TABLE IF EXISTS nfe_sefaz_sweep")
    _logger.info("liber_nfe_xml: tabelas da varredura SEFAZ DFe removidas.")
