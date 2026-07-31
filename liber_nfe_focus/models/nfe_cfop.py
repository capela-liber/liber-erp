# -*- coding: utf-8 -*-
"""O CFOP é tabela de referência, não lugar de configuração.

Os 619 códigos do Anexo II do Convênio SINIEF s/nº (CONFAZ) entram como estão,
com a descrição normativa. O que a casa configura — natureza, finalidade, CST,
cBenef, IBS/CBS — mora em `nfe.operacao`, porque é atributo da **operação**, e
a operação é o CFOP sem o primeiro dígito.

Enquanto a configuração morou aqui, 5101 e 6101 carregavam a mesma coisa
escrita duas vezes, e havia um teste só para afirmar que as duas cópias não
tinham divergido. O teste era o sintoma.
"""

from odoo import models


class NfeCfop(models.Model):
    _inherit = 'nfe.cfop'

    # O CFOP é tabela nacional: dois registros com o mesmo código são sempre
    # erro, e um erro que não aparece — quem escolhe na tela vê duas linhas
    # iguais e a nota sai com a natureza de uma ou de outra. As duplicatas que
    # existiam são fundidas na instalação; esta constraint impede que voltem.
    _codigo_unico = models.Constraint(
        'UNIQUE(code)',
        "Já existe um CFOP com este código. O CFOP é tabela nacional: cada "
        "código existe uma vez só.")

    def _operacao(self):
        """A operação que este CFOP representa: sentido + três últimos dígitos.

        É por aqui que um CFOP escolhido à mão — o caminho da exportação, que
        não se deduz — recupera natureza, finalidade e tributação.
        """
        self.ensure_one()
        codigo = (self.code or '').strip()
        if len(codigo) != 4 or not codigo.isdigit():
            return self.env['nfe.operacao']
        sentido = 'entrada' if codigo[0] in '123' else 'saida'
        return self.env['nfe.operacao'].search(
            [('code', '=', codigo[1:]), ('sentido', '=', sentido)], limit=1)
