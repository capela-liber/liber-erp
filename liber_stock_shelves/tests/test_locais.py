# -*- coding: utf-8 -*-
"""O interruptor "Locais de armazenamento" como código, e o que ele libera.

A pergunta não é "o grupo existe": é se a TELA mostra a prateleira e se um
livro consegue mudar de prateleira. Por isso dois testes perguntam à view e
ao picking, não ao ACL -- é o que a casa aprendeu em 22/08/2026 com o
Editorial nas compras (ORM verde, tela com Access Error).
"""

from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_stock_shelves import ligar_locais_de_armazenamento


@tagged('post_install', '-at_install', 'liber_stock_shelves')
class TestLocaisDeArmazenamento(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.grupo_locais = cls.env.ref('stock.group_stock_multi_locations')
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        Loc = cls.env['stock.location']
        cls.prateleira_a = Loc.create({
            'name': 'TST-000001', 'usage': 'internal',
            'location_id': cls.warehouse.lot_stock_id.id})
        cls.prateleira_b = Loc.create({
            'name': 'TST-000002', 'usage': 'internal',
            'location_id': cls.warehouse.lot_stock_id.id})
        cls.livro = cls.env['product.product'].create({
            'name': 'Os Sertões', 'type': 'consu', 'is_storable': True})
        cls.env['stock.quant']._update_available_quantity(
            cls.livro, cls.prateleira_a, 10)

        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def _usuario(nome, login, *xmlids):
            return Users.create({
                'name': nome, 'login': login,
                'company_id': cls.company.id,
                'company_ids': [(6, 0, [cls.company.id])],
                'group_ids': [(4, cls.env.ref(x).id) for x in xmlids],
            })

        # Um usuário interno qualquer, sem função: é o nível em que o
        # interruptor do Odoo opera (base.group_user), então é ele que prova.
        cls.interno = _usuario('Interno', 'interno@shelves.test',
                               'base.group_user')
        cls.deposito = _usuario('Depósito', 'deposito@shelves.test',
                                'stock.group_stock_user')
        cls.gerente_deposito = _usuario('Gerente do depósito',
                                        'gerente@shelves.test',
                                        'stock.group_stock_manager')
        cls.env.flush_all()
        cls.env.registry.clear_cache()

    # -- o interruptor -------------------------------------------------------

    def test_usuario_interno_implica_locais(self):
        self.assertIn(self.grupo_locais,
                      self.env.ref('base.group_user').implied_ids)
        for u in (self.interno, self.deposito, self.gerente_deposito):
            self.assertTrue(
                u.has_group('stock.group_stock_multi_locations'),
                '%s não enxerga locais de armazenamento' % u.name)

    def test_gerente_comercial_enxerga_a_prateleira(self):
        """A queixa que originou o módulo (08/10/2026)."""
        grupo = self.env.ref('liber_roles.group_comercial_gerente',
                             raise_if_not_found=False)
        if not grupo:
            self.skipTest('liber_roles não está nesta base')
        gerente = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Gerente comercial', 'login': 'gc@shelves.test',
                'company_id': self.company.id,
                'company_ids': [(6, 0, [self.company.id])],
                'group_ids': [(4, grupo.id)]})
        self.env.registry.clear_cache()
        self.assertTrue(gerente.has_group('stock.group_stock_multi_locations'))
        prateleira = self.env['stock.location'].with_user(gerente).browse(
            self.prateleira_a.id)
        self.assertEqual(prateleira.name, 'TST-000001')

    def test_transferencia_interna_ativa_em_todo_armazem(self):
        armazens = self.env['stock.warehouse'].with_context(
            active_test=False).search([])
        self.assertTrue(armazens)
        for w in armazens:
            self.assertTrue(w.int_type_id, '%s sem tipo INT' % w.name)
            self.assertTrue(w.int_type_id.active,
                            'INT de %s está arquivado' % w.name)

    def test_gancho_reativa_o_int_e_e_idempotente(self):
        tipo = self.warehouse.int_type_id
        tipo.active = False
        self.assertEqual(ligar_locais_de_armazenamento(self.env),
                         self.warehouse)
        self.assertTrue(tipo.active)
        # Segunda rodada: nada a fazer, e não quebra.
        self.assertFalse(ligar_locais_de_armazenamento(self.env))
        self.assertTrue(tipo.active)

    # -- a tela ---------------------------------------------------------------

    def _de_para_na_tela(self, usuario):
        """Se o formulário da transferência mostra o campo Para a esse usuário.

        O core declara o campo duas vezes: uma invisível para quem não tem o
        grupo e outra visível, com `groups=`, para quem tem. O `get_view`
        resolve o `groups=` pelo usuário e devolve só a versão dele -- então
        a pergunta é a mesma que o navegador faz. A coluna homônima da lista
        de linhas (`column_invisible`) não conta: é outro campo, sempre oculto.
        """
        arch = self.env['stock.picking'].with_user(usuario).get_view(
            view_type='form')['arch']
        nos = etree.fromstring(arch).xpath(
            "//field[@name='location_dest_id'][not(@column_invisible)]")
        self.assertTrue(nos, 'o formulário não declara location_dest_id')
        return any(n.get('invisible') not in ('1', 'True') for n in nos)

    def test_a_transferencia_mostra_de_para(self):
        # Quem pergunta é quem abre a transferência: o usuário do depósito
        # (um interno sem Inventário nem lê stock.picking).
        self.assertTrue(self._de_para_na_tela(self.deposito))
        # Contraprova: sem a aresta, o mesmo usuário deixa de ver o campo. É
        # o estado em que o banco chegou da migração.
        self.env.ref('base.group_user').write(
            {'implied_ids': [(3, self.grupo_locais.id)]})
        self.env.registry.clear_cache()
        self.assertFalse(self._de_para_na_tela(self.deposito))

    # -- o movimento ----------------------------------------------------------

    def _saldo(self, local):
        return self.env['stock.quant']._get_available_quantity(
            self.livro, local)

    def test_usuario_do_deposito_move_livro_entre_prateleiras(self):
        Picking = self.env['stock.picking'].with_user(self.deposito)
        picking = Picking.create({
            'picking_type_id': self.warehouse.int_type_id.id,
            'location_id': self.prateleira_a.id,
            'location_dest_id': self.prateleira_b.id,
            'move_ids': [(0, 0, {
                'product_id': self.livro.id,
                'product_uom_qty': 3,
                'product_uom': self.livro.uom_id.id,
                'location_id': self.prateleira_a.id,
                'location_dest_id': self.prateleira_b.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        self.assertEqual(picking.state, 'assigned')
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        self.assertEqual(self._saldo(self.prateleira_a), 7)
        self.assertEqual(self._saldo(self.prateleira_b), 3)
        self.assertEqual(
            picking.move_line_ids.location_dest_id, self.prateleira_b)

    def test_realocar_e_do_administrador(self):
        quant = self.env['stock.quant'].search([
            ('product_id', '=', self.livro.id),
            ('location_id', '=', self.prateleira_a.id)])
        self.assertEqual(len(quant), 1)
        # Quem só opera o depósito não realoca em lote.
        with self.assertRaises(AccessError):
            self.env['stock.quant.relocate'].with_user(self.deposito).create({
                'quant_ids': [(6, 0, quant.ids)],
                'dest_location_id': self.prateleira_b.id})
        # O administrador do Inventário realoca, e a prateleira muda inteira.
        wiz = self.env['stock.quant.relocate'].with_user(
            self.gerente_deposito).create({
                'quant_ids': [(6, 0, quant.ids)],
                'dest_location_id': self.prateleira_b.id,
                'message': 'Remanejo de teste'})
        wiz.action_relocate_quants()
        self.assertEqual(self._saldo(self.prateleira_a), 0)
        self.assertEqual(self._saldo(self.prateleira_b), 10)
