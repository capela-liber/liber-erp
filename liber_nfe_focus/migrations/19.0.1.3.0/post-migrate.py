# -*- coding: utf-8 -*-
"""Leva a configuração fiscal do CFOP para a operação.

Até a 19.0.1.2.0 a configuração morava no `nfe.cfop` -- e por isso 5101 e 6101
carregavam a mesma coisa escrita duas vezes. Agora ela mora em `nfe.operacao`,
que é o CFOP sem o primeiro dígito, e o dígito nasce do destino.

Esta migração repõe os impostos: quem apontava para o CFOP 5917 passa a apontar
para a operação de saída 917. O par 5xxx/6xxx converge para a MESMA operação,
então dois impostos podem cair no mesmo destino -- e é isso mesmo, era a
duplicação que se queria acabar. O que existia continua funcionando; o que
sobra é ruído que o botão "Gerar impostos por operação" não vai recriar.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    from odoo import SUPERUSER_ID
    from odoo.api import Environment
    env = Environment(cr, SUPERUSER_ID, {})

    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'account_tax' AND column_name = 'nfe_cfop_id'
    """)
    if not cr.fetchone():
        return

    Operacao = env['nfe.operacao']
    cr.execute("""
        SELECT t.id, c.code
        FROM account_tax t JOIN nfe_cfop c ON c.id = t.nfe_cfop_id
        WHERE t.nfe_cfop_id IS NOT NULL
    """)
    religados = 0
    for tax_id, codigo in cr.fetchall():
        if not codigo or len(codigo) != 4:
            continue
        sentido = 'entrada' if codigo[0] in '123' else 'saida'
        operacao = Operacao.search(
            [('code', '=', codigo[1:]), ('sentido', '=', sentido)], limit=1)
        if not operacao:
            _logger.warning(
                "Imposto %s aponta para o CFOP %s e não há operação "
                "correspondente; ficou sem operação.", tax_id, codigo)
            continue
        cr.execute("UPDATE account_tax SET nfe_operacao_id = %s WHERE id = %s",
                   (operacao.id, tax_id))
        religados += 1
    _logger.info("Impostos religados do CFOP para a operação: %d.", religados)

    # A operação padrão da empresa vem do CFOP interno que ela usava.
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'res_company' AND column_name = 'focus_cfop_interno_id'
    """)
    if cr.fetchone():
        cr.execute("""
            SELECT co.id, c.code FROM res_company co
            JOIN nfe_cfop c ON c.id = co.focus_cfop_interno_id
        """)
        for company_id, codigo in cr.fetchall():
            if not codigo or len(codigo) != 4:
                continue
            operacao = Operacao.search(
                [('code', '=', codigo[1:]),
                 ('sentido', '=', 'entrada' if codigo[0] in '123' else 'saida')],
                limit=1)
            if operacao:
                cr.execute(
                    "UPDATE res_company SET focus_operacao_padrao_id = %s "
                    "WHERE id = %s", (operacao.id, company_id))
