# -*- coding: utf-8 -*-
"""A empresa segue a Equipe. O chamado chega na edlab e é repassado para a
n-1: trocar a Equipe tem de mudar a empresa, senão a n-1 não enxerga o
chamado (a ir.rule do ticket filtra por company_id)."""
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import SupportCase


@tagged('post_install', '-at_install')
class TestEmpresaSegueEquipe(SupportCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Empresas são REAPROVEITADAS, nunca criadas (res.company.create
        # estoura no NOT NULL de fiscalyear_last_day quando o account está
        # instalado).
        outras = cls.env['res.company'].search(
            [('id', '!=', cls.company.id)], order='id', limit=1)
        cls.outra_company = outras
        if outras:
            cls.team_outra = cls.env['liber.support.team'].create({
                'name': 'Comercial n-1 Test',
                'company_id': outras.id,
                'resource_calendar_id': cls.calendar.id,
                'alias_name': 'comercial-n1-test',
            })

    def _ticket(self, **vals):
        base = {'name': 'Envio de livros', 'team_id': self.team.id}
        base.update(vals)
        return self.Ticket.create(base)

    # --- caminho feliz -------------------------------------------------

    def test_trocar_equipe_muda_a_empresa(self):
        if not self.outra_company:
            self.skipTest("o banco só tem uma empresa")
        ticket = self._ticket()
        self.assertEqual(ticket.company_id, self.company)
        ticket.write({'team_id': self.team_outra.id})
        self.assertEqual(ticket.company_id, self.outra_company,
                         "a empresa tem de seguir a Equipe nova")

    def test_onchange_mostra_a_empresa_antes_de_salvar(self):
        if not self.outra_company:
            self.skipTest("o banco só tem uma empresa")
        ticket = self._ticket()
        ticket.team_id = self.team_outra
        ticket._onchange_team_id_company()
        self.assertEqual(ticket.company_id, self.outra_company)

    # --- borda ---------------------------------------------------------

    def test_empresa_explicita_na_mesma_escrita_manda(self):
        """Quem decide a empresa na mesma escrita não é sobrescrito."""
        if not self.outra_company:
            self.skipTest("o banco só tem uma empresa")
        ticket = self._ticket()
        ticket.write({'team_id': self.team_outra.id,
                      'company_id': self.company.id})
        self.assertEqual(ticket.company_id, self.company)

    def test_limpar_a_equipe_nao_mexe_na_empresa(self):
        ticket = self._ticket()
        ticket.write({'team_id': False})
        self.assertEqual(ticket.company_id, self.company,
                         "sem Equipe não há empresa para seguir")

    def test_escrita_sem_equipe_nao_mexe_na_empresa(self):
        ticket = self._ticket()
        ticket.write({'priority': '1'})
        self.assertEqual(ticket.company_id, self.company)

    # --- erro ----------------------------------------------------------

    def test_repasse_por_quem_nao_e_da_equipe_de_destino_e_recusado(self):
        """A ir.rule do chamado é medida DEPOIS da escrita: quem repassa
        para uma equipe de que não é membro perde o registro na saída, e o
        Odoo recusa. Vale saber antes do primeiro susto na tela."""
        if not self.outra_company:
            self.skipTest("o banco só tem uma empresa")
        atendente = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Atendente só da casa',
                'login': 'atendente_so_da_casa_test',
                'company_id': self.company.id,
                'company_ids': [(6, 0, [self.company.id,
                                        self.outra_company.id])],
                'group_ids': [(4, self.env.ref(
                    'liber_support.group_support_user').id)],
            })
        self.team.write({'member_ids': [(4, atendente.id)]})
        ticket = self._ticket()
        with self.assertRaises(AccessError):
            ticket.with_user(atendente).write(
                {'team_id': self.team_outra.id})

    def test_equipe_inexistente_estoura(self):
        """Equipe que não existe: a leitura da empresa da Equipe estoura
        antes de gravar qualquer coisa."""
        from odoo.exceptions import MissingError
        ticket = self._ticket()
        with self.assertRaises(MissingError):
            ticket.write({'team_id': 999999999})
