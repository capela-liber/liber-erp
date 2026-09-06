# -*- coding: utf-8 -*-
"""A varredura SEFAZ DFe sai do módulo.

Ela nunca correu em produção: nenhuma varredura registrada, nenhuma nota com
origem ``sefaz``, nenhuma empresa habilitada. O que sobra dela no banco é o
cron diário, o menu, as views, os campos da empresa e uma tabela vazia. O
``_process_end`` do upgrade apaga tudo o que o módulo deixou de declarar;
aqui só se resolve o que não pode esperar por ele:

- as views: a aba "SEFAZ (DFe)" herdada no formulário da empresa aponta
  para campos que o modelo já não tem, e o upgrade valida o formulário
  inteiro ao carregar qualquer view que o herde — antes de chegar ao
  ``_process_end`` que a apagaria;
- o cron, que um worker ainda poderia disparar durante o upgrade contra um
  modelo que já não existe no registry — vai inteiro, com a ação de servidor
  que ele delega, porque o ``_process_end`` solta a linha do cron sem a ação
  e deixa a ação presa pela chave estrangeira;
- a origem das notas, que perde o valor ``sefaz`` da seleção e cairia em
  nulo — ``manual`` é o padrão do campo e o que a lista já mostra.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE id IN (SELECT res_id FROM ir_model_data
                     WHERE module = 'liber_nfe_xml'
                       AND model = 'ir.ui.view'
                       AND name IN ('view_company_form_sefaz',
                                    'view_nfe_sefaz_sweep_list',
                                    'view_nfe_sefaz_sweep_form'))
    """)
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'liber_nfe_xml'
          AND model = 'ir.ui.view'
          AND name IN ('view_company_form_sefaz',
                       'view_nfe_sefaz_sweep_list',
                       'view_nfe_sefaz_sweep_form')
    """)
    cr.execute("""
        DELETE FROM ir_cron
        WHERE id IN (SELECT res_id FROM ir_model_data
                     WHERE module = 'liber_nfe_xml'
                       AND model = 'ir.cron'
                       AND name = 'cron_nfe_sefaz_sweep')
    """)
    cr.execute("""
        DELETE FROM ir_act_server
        WHERE id IN (SELECT res_id FROM ir_model_data
                     WHERE module = 'liber_nfe_xml'
                       AND model = 'ir.actions.server'
                       AND name = 'cron_nfe_sefaz_sweep_ir_actions_server')
    """)
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'liber_nfe_xml'
          AND name IN ('cron_nfe_sefaz_sweep',
                       'cron_nfe_sefaz_sweep_ir_actions_server')
    """)
    cr.execute("""
        UPDATE nfe_xml_panel SET source = 'manual' WHERE source = 'sefaz'
    """)
    if cr.rowcount:
        _logger.warning("liber_nfe_xml: %s nota(s) baixadas da SEFAZ passam a "
                        "constar como envio manual.", cr.rowcount)
    _logger.info("liber_nfe_xml: varredura SEFAZ DFe desligada; o upgrade "
                 "remove o modelo, o cron, o menu e os campos da empresa.")
