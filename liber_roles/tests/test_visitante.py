# -*- coding: utf-8 -*-
"""O visitante enxerga tudo e não grava nada -- menos o chatter.

Este teste existe porque a promessa do visitante é uma promessa de segurança
feita a uma conta que vai circular em público. Promessa de segurança sem teste
é intenção.
"""

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_roles')
class TestVisitante(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        company = cls.env.ref('base.main_company')
        cls.visitor = Users.create({
            'name': 'Visitante', 'login': 'visitante@liber.test',
            'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
            'group_ids': [(4, cls.env.ref('liber_roles.group_visitante').id)],
        })
        cls.seller = Users.create({
            'name': 'Comercial', 'login': 'comercial@liber.test',
            'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
            'group_ids': [(4, cls.env.ref('liber_roles.group_comercial_gerente').id)],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Livraria de Teste'})
        cls.env.flush_all()
        cls.env.registry.clear_cache()

    @property
    def as_visitor(self):
        return self.env(user=self.visitor.id, su=False)

    # ------------------------------------------------------------ enxerga
    def test_visitante_le_o_sistema(self):
        """Nenhuma tela fica fechada: é uma demonstração, não uma vitrine."""
        env = self.as_visitor
        for model in ('res.partner', 'sale.order', 'account.move', 'product.template'):
            env[model].search([], limit=5).mapped('display_name')

    # ------------------------------------------------------------ não grava
    def test_visitante_nao_emite_pedido(self):
        with self.assertRaises(AccessError):
            self.as_visitor['sale.order'].create({'partner_id': self.partner.id})

    def test_visitante_nao_altera_cadastro(self):
        with self.assertRaises(AccessError):
            self.as_visitor['res.partner'].browse(self.partner.id).write(
                {'comment': 'alterado pelo visitante'})

    def test_visitante_nao_mexe_na_contabilidade(self):
        with self.assertRaises(AccessError):
            self.as_visitor['account.move'].create(
                {'move_type': 'out_invoice', 'partner_id': self.partner.id})

    def test_visitante_nao_apaga(self):
        with self.assertRaises(AccessError):
            self.as_visitor['res.partner'].browse(self.partner.id).unlink()

    def test_recusa_explica_o_modo_visitante(self):
        """A mensagem é para quem está vendo o sistema pela primeira vez."""
        with self.assertRaises(AccessError) as e:
            self.as_visitor['sale.order'].create({'partner_id': self.partner.id})
        self.assertIn('Modo visitante', str(e.exception))

    # ------------------------------------------------------------ conversa
    def test_visitante_manda_mensagem(self):
        """Ler dá direito a comentar -- o regime que o portal já usa."""
        msg = self.as_visitor['res.partner'].browse(self.partner.id).message_post(
            body="Olá da apresentação!")
        self.assertTrue(msg)
        self.assertEqual(msg.author_id, self.visitor.partner_id)

    # -------------------------------------------------- ninguém mais regride
    def test_usuario_de_verdade_continua_gravando(self):
        """O guarda vale para o visitante, não para a casa."""
        env = self.env(user=self.seller.id, su=False)
        order = env['sale.order'].create({'partner_id': self.partner.id})
        self.assertTrue(order)
        env['res.partner'].browse(self.partner.id).write({'comment': 'legítimo'})
