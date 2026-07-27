# -*- coding: utf-8 -*-
"""O guarda em ir.model.access.check.

A maior parte destes testes ataca `_capela_ai_blocked` diretamente, em vez de
passar pelo ORM inteiro. É de propósito: passar pelo ORM misturaria a recusa do
guarda com as ACLs normais do modelo de teste, e um teste que passa pelo motivo
errado é pior que nenhum. Há um teste de ponta a ponta no fim para provar que a
ligação existe.
"""

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from ..models.ir_model_access import CTX_PLANNING, CTX_WRITES


@tagged('post_install', '-at_install')
class TestGuard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({
            'name': 'Agente Testes',
            'login': 'capela_ai_test_guard',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        # `env.su` desliga o guarda por desenho (ver o docstring do módulo).
        # Todo teste precisa rodar como gente, não como superusuário.
        cls.access = cls.env['ir.model.access'].with_user(cls.user)

    def _blocked(self, model, mode, **ctx):
        return self.access.with_context(**ctx)._capela_ai_blocked(model, mode)

    # -- fora de ação do agente: o guarda não opina -------------------------

    def test_sem_contexto_nao_bloqueia(self):
        """Usuário mexendo no Odoo normalmente não passa por aqui."""
        self.assertIsNone(self._blocked('res.partner', 'write'))
        self.assertIsNone(self._blocked('res.partner', 'create'))
        self.assertIsNone(self._blocked('res.partner', 'unlink'))

    def test_leitura_nunca_bloqueia(self):
        """Leitura é assunto das ACLs da pessoa, e é de lá que vem o limite."""
        self.assertIsNone(self._blocked('res.partner', 'read', **{CTX_PLANNING: True}))
        self.assertIsNone(self._blocked('res.partner', 'read', **{CTX_WRITES: ()}))

    # -- planejando: proposta não grava, ponto ------------------------------

    def test_planejando_bloqueia_qualquer_escrita(self):
        for mode in ('create', 'write', 'unlink'):
            with self.subTest(mode=mode):
                self.assertTrue(self._blocked('res.partner', mode, **{CTX_PLANNING: True}))

    def test_planejando_bloqueia_ate_o_chatter(self):
        """Nem mail.message: montar proposta é ato de leitura, inteiro."""
        self.assertTrue(self._blocked('mail.message', 'create', **{CTX_PLANNING: True}))

    # -- aplicando: só o declarado, e nunca apagar --------------------------

    def test_aplicando_permite_o_declarado(self):
        self.assertIsNone(
            self._blocked('res.partner', 'create', **{CTX_WRITES: ('res.partner',)})
        )
        self.assertIsNone(
            self._blocked('res.partner', 'write', **{CTX_WRITES: ('res.partner',)})
        )

    def test_aplicando_recusa_o_nao_declarado(self):
        """A ferramenta declarou res.partner; mexer em res.country é falha dela."""
        self.assertTrue(
            self._blocked('res.country', 'write', **{CTX_WRITES: ('res.partner',)})
        )

    def test_aplicando_recusa_unlink_mesmo_do_declarado(self):
        """Apagar não é uma capacidade que se concede com cuidado."""
        message = self._blocked('res.partner', 'unlink', **{CTX_WRITES: ('res.partner',)})
        self.assertTrue(message)
        self.assertIn('apaga', message.lower())

    def test_aplicando_permite_o_chatter(self):
        """O rastro de auditoria precisa poder ser escrito."""
        self.assertIsNone(
            self._blocked('mail.message', 'create', **{CTX_WRITES: ('res.partner',)})
        )

    # -- a fronteira declarada em voz alta ----------------------------------

    def test_sudo_passa_e_isso_e_deliberado(self):
        """Não é descuido: criar documento no Odoo grava sequência e chatter
        por baixo do usuário. Contra sudo a defesa é test_no_sudo.py."""
        como_su = self.env['ir.model.access']  # env de teste roda como superusuário
        self.assertTrue(como_su.env.su)
        self.assertIsNone(
            como_su.with_context(**{CTX_PLANNING: True})._capela_ai_blocked('res.partner', 'write')
        )

    # -- ponta a ponta: o guarda está mesmo ligado no ORM -------------------

    def test_ligacao_com_o_orm(self):
        Partner = self.env['res.partner'].with_user(self.user)
        with self.assertRaises(AccessError):
            Partner.with_context(**{CTX_PLANNING: True}).create({'name': 'Não deve existir'})
