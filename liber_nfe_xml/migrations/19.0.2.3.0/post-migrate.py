# -*- coding: utf-8 -*-
from odoo.addons.liber_nfe_xml.models.nfe_cfop import classify_cfops


def migrate(cr, version):
    """A classificação do CFOP é regra, não configuração: reaplica a cada upgrade.

    Também limpa a duplicata que a primeira tentativa criou -- os CFOPs vieram
    semeados noupdate, então um registro com o mesmo external id nunca era escrito,
    e um com id novo duplicava o CFOP (dois 5113).
    """
    from odoo.api import Environment
    env = Environment(cr, 1, {})
    duplicados = env['nfe.cfop'].search([]).grouped('code')
    for code, cfops in duplicados.items():
        if len(cfops) > 1:
            # fica o mais antigo (o que os documentos já referenciam)
            manter = cfops.sorted('id')[0]
            manter.write({
                'consignment_effect': next(
                    (c.consignment_effect for c in cfops if c.consignment_effect), False),
            })
            (cfops - manter).unlink()
    classify_cfops(env)
