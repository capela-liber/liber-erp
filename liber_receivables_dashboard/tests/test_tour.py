# -*- coding: utf-8 -*-
"""O Histórico dos Recebíveis pela tela, no perfil do Financeiro.

O `test_snapshot.py` prova o que a foto guarda. Este prova o caminho: quem
tem contabilidade abre o histórico, vê a lista agrupada e tem à mão a ação
de fotografar hoje. Não é o admin de propósito: admin passa em tudo.
"""
from odoo.tests import HttpCase, tagged



# A senha do usuário de tour é IGUAL AO LOGIN -- é assim que o `start_tour`
# entra. O literal fica no login e a senha o referencia: escrito das duas
# vezes, ele casa com a varredura de segredos do publish_liber_erp.sh e barra
# a publicação inteira.
LOGIN = 'financeiro_historico_tour'

@tagged('post_install', '-at_install', 'liber_receivables_dashboard_tour')
class TestReceivablesHistoryTour(HttpCase):

    def test_receivables_history_tour(self):
        empresa = self.env.company
        # Uma foto, para a lista não abrir vazia.
        self.env['liber.receivables.snapshot']._tirar_foto()
        grupos = [self.env.ref('base.group_user').id,
                  self.env.ref('account.group_account_user').id]
        readonly = self.env.ref('account.group_account_readonly', False)
        if readonly:
            grupos.append(readonly.id)
        usuario = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Financeiro do Tour', 'login': LOGIN,
            'password': LOGIN, 'lang': 'en_US',
            'company_id': empresa.id, 'company_ids': [(6, 0, [empresa.id])],
            'group_ids': [(6, 0, grupos)],
        })
        self.assertTrue(usuario.exists())
        self.start_tour('/odoo', 'liber_receivables_history_tour',
                        login=LOGIN)
