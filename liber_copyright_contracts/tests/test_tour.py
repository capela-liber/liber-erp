# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestCopyrightContractsTour(HttpCase):
    def test_copyright_contracts_tour(self):
        """Drive the whole contract life end to end through the real UI:
        create -> the renewal term auto-fills from the dates -> add a royalty
        line (beneficiary x work) with two copies tiers and a recoupable
        advance -> save -> validate -> renew -> reassign the responsible via the
        Action menu -> cancel."""
        # O tour é escrito em inglês, e alguns passos só existem por texto: um
        # item do menu de ação não tem atributo estável no DOM, só o rótulo.
        # No banco de teste o admin está em pt_BR, então cada tradução que
        # entra derruba um passo -- foi assim que "Royalties" (aba) e
        # "Reassign" (ação) quebraram sem que nada de verdade tivesse mudado.
        # A sessão do tour roda em inglês; a tradução segue conferida na tela,
        # não aqui.
        self.env.ref('base.user_admin').lang = 'en_US'
        self.start_tour(
            "/odoo", "copyright_contracts_tour", login="admin"
        )
