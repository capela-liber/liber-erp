# -*- coding: utf-8 -*-
from odoo import models


class ConsignmentAgreement(models.Model):
    _inherit = 'consignment.agreement'

    def _create_shelf_location(self):
        """Stamp the consignment stock account on the shelf as it is created, so
        stock_account re-qualifies its value into that account.

        O `sudo()` é o mesmo de sempre, e faltava aqui (27/08/2026). O
        liber_soc_agreements pôs a CRIAÇÃO da prateleira em sudo em 26/08 e o
        bloqueio da gerente comercial continuou de pé, agora com outra frase:
        "Você não tem permissão para MODIFICAR registros de 'Locais de
        inventário'". Criar deixou de pedir Inventário; carimbar a conta em
        cima do local recém-criado ainda pedia -- e é escrita, não criação, de
        modo que o conserto anterior passava ao largo dela.

        O teste que existia não pegava porque a base de teste nasce SEM
        `consignment_stock_account_id`: sem conta, este método não escreve nada
        e a linha nunca roda. A produção tem a conta preenchida nas empresas
        que consignam, e por isso quebrava só lá. O teste novo
        (tests/test_acl_prateleira_valorada.py) preenche a conta de propósito.

        A prateleira não é gaveta que o Comercial abriu no Inventário: é
        consequência de ativar o contrato, e a conta que ela carrega vem da
        ficha da empresa, não da tela. Quem tem o direito de ativar tem o
        efeito inteiro.
        """
        location = super()._create_shelf_location()
        account = self.company_id.consignment_stock_account_id
        if account:
            location.sudo().valuation_account_id = account.id
        return location
