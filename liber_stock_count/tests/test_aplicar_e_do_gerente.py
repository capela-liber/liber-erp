# -*- coding: utf-8 -*-
"""Contar é de quem está no depósito; aplicar é do gerente.

O que se trava aqui são as DUAS metades da promessa. A de cima: o assistente
continua contando -- preenche "Contado", e nada do que digitou se perde quando
a recusa aparece. A de baixo, que é a perigosa: nenhuma das portas por onde o
core aplica um ajuste (o Aplicar da linha, o Aplicar tudo com motivo, a ficha
do produto) deixa passar quem não é administrador do Inventário. Menu
escondido não é prova; o ORM é.
"""

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_stock_count')
class TestAplicarEDoGerente(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def _grupo(casa, core):
            # O perfil da casa quando o liber_roles está instalado; senão o
            # grupo do core que ele embrulha.
            return cls.env.ref(casa, raise_if_not_found=False) \
                or cls.env.ref(core)

        def _usuario(nome, login, *grupos):
            return Users.create({
                'name': nome, 'login': login,
                'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
                'group_ids': [(6, 0, [g.id for g in grupos])],
            })

        cls.assistente = _usuario(
            'Assistente do Depósito', 'conta@liber.test',
            _grupo('liber_roles.group_logistica_assistente',
                   'stock.group_stock_user'))
        cls.gerente = _usuario(
            'Gerente do Depósito', 'aplica@liber.test',
            _grupo('liber_roles.group_logistica_gerente',
                   'stock.group_stock_manager'))
        # A ficha do produto exige escrita em product.product, que nenhum
        # perfil da Logística tem (o Gerente da casa configura o depósito,
        # não o catálogo). Para provar a porta da ficha nos dois sentidos,
        # dois administradores do sistema: um com estoque em nível de
        # usuário, outro em nível de administrador do Inventário.
        cls.outro_gerente = _usuario(
            'Gerente de Outra Área', 'ficha@liber.test',
            cls.env.ref('stock.group_stock_user'),
            cls.env.ref('base.group_system'))
        cls.gerente_com_ficha = _usuario(
            'Administrador do Inventário', 'ficha.gerente@liber.test',
            cls.env.ref('stock.group_stock_manager'),
            cls.env.ref('base.group_system'))

        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        cls.prateleira = cls.env['stock.location'].create({
            'name': 'TST-000007', 'usage': 'internal',
            'location_id': cls.warehouse.lot_stock_id.id})
        cls.livro = cls.env['product.product'].create({
            'name': 'Livro da Contagem', 'type': 'consu',
            'is_storable': True})
        Quant = cls.env['stock.quant']
        Quant._update_available_quantity(cls.livro, cls.prateleira, 10)
        cls.quant = Quant._gather(cls.livro, cls.prateleira, strict=True)
        cls.env.flush_all()
        cls.env.registry.clear_cache()

    # -- ajudantes ----------------------------------------------------------
    def _como(self, usuario):
        """O quant visto por um usuário, no modo de inventário da tela."""
        return self.quant.with_user(usuario).with_context(inventory_mode=True)

    def _contar(self, usuario, quantos):
        self._como(usuario).write({'inventory_quantity': quantos})

    def _ajustes(self):
        return self.env['stock.move.line'].search([
            ('product_id', '=', self.livro.id), ('state', '=', 'done'),
            '|', ('location_id.usage', '=', 'inventory'),
            ('location_dest_id.usage', '=', 'inventory')])

    # -- a metade de cima: o assistente conta ---------------------------------
    def test_assistente_conta(self):
        self._contar(self.assistente, 7)
        self.assertEqual(self.quant.inventory_quantity, 7)
        self.assertTrue(self.quant.inventory_quantity_set)
        self.assertEqual(self.quant.inventory_diff_quantity, -3)
        # Contar não mexe no estoque.
        self.assertEqual(self.quant.quantity, 10)
        self.assertFalse(self._ajustes())

    def test_assistente_limpa_a_propria_contagem(self):
        self._contar(self.assistente, 7)
        self._como(self.assistente).action_clear_inventory_quantity()
        self.assertFalse(self.quant.inventory_quantity_set)
        self.assertEqual(self.quant.quantity, 10)

    def test_assistente_cria_linha_para_livro_fora_da_lista(self):
        """O livro estava na prateleira e não na lista: a contagem o cria."""
        outro = self.env['product.product'].create({
            'name': 'Livro Achado', 'type': 'consu', 'is_storable': True})
        quant = self.env['stock.quant'].with_user(self.assistente).with_context(
            inventory_mode=True).create({
                'product_id': outro.id,
                'location_id': self.prateleira.id,
                'inventory_quantity': 2})
        self.assertTrue(quant.inventory_quantity_set)
        self.assertEqual(quant.inventory_quantity, 2)
        self.assertEqual(quant.quantity, 0, 'criar a linha não é aplicar')

    # -- a metade de baixo: só o gerente aplica -------------------------------
    def test_assistente_nao_aplica_pela_linha(self):
        self._contar(self.assistente, 7)
        with self.assertRaises(AccessError):
            self._como(self.assistente).action_apply_inventory()
        self.assertEqual(self.quant.quantity, 10)
        self.assertFalse(self._ajustes())
        # A contagem recusada não se perde: fica esperando o gerente.
        self.assertTrue(self.quant.inventory_quantity_set)
        self.assertEqual(self.quant.inventory_quantity, 7)

    def test_assistente_nao_aplica_pelo_motivo(self):
        """O cabeçalho "Aplicar" abre o assistente de motivo; a porta é a mesma."""
        self._contar(self.assistente, 7)
        wizard = self.env['stock.inventory.adjustment.name'].with_user(
            self.assistente).create({
                'quant_ids': [(6, 0, [self.quant.id])],
                'inventory_adjustment_name': 'Contagem de outubro'})
        with self.assertRaises(AccessError):
            wizard.action_apply()
        self.assertEqual(self.quant.quantity, 10)

    def test_assistente_nao_aplica_tudo(self):
        self._contar(self.assistente, 7)
        with self.assertRaises(AccessError):
            self._como(self.assistente).with_context(
                active_domain=[('product_id', '=', self.livro.id)]
            ).action_apply_all()

    def test_quem_nao_e_do_inventario_nao_muda_em_maos_pela_ficha(self):
        """A ficha do produto é a porta que a trava do quant não veria.

        O core cria o quant como superusuário nesse caminho; sem a guarda no
        inverso, qualquer um com escrita no produto ajustava o estoque.
        """
        produto = self.livro.with_user(self.outro_gerente)
        # Ele escreve no produto -- o que se recusa é só a quantidade.
        produto.write({'description': 'edição revista'})
        with self.assertRaisesRegex(AccessError, 'Inventory administrator'):
            produto.write({'qty_available': 7})
        self.assertEqual(self.quant.quantity, 10)
        self.assertFalse(self._ajustes())

    # -- o gerente aplica ------------------------------------------------------
    def test_gerente_aplica_a_contagem_do_assistente(self):
        self._contar(self.assistente, 7)
        self._como(self.gerente).action_apply_inventory()
        self.assertEqual(self.quant.quantity, 7)
        self.assertFalse(self.quant.inventory_quantity_set)
        ajuste = self._ajustes()
        self.assertEqual(len(ajuste), 1)
        self.assertEqual(ajuste.quantity, 3)
        self.assertEqual(ajuste.location_id, self.prateleira)
        self.assertEqual(ajuste.location_dest_id.usage, 'inventory')

    def test_gerente_aplica_com_motivo(self):
        self._contar(self.assistente, 12)
        wizard = self.env['stock.inventory.adjustment.name'].with_user(
            self.gerente).create({
                'quant_ids': [(6, 0, [self.quant.id])],
                'inventory_adjustment_name': 'Inventário de outubro'})
        wizard.action_apply()
        self.assertEqual(self.quant.quantity, 12)
        ajuste = self._ajustes()
        self.assertEqual(len(ajuste), 1)
        self.assertEqual(ajuste.quantity, 2)
        self.assertEqual(ajuste.reference, 'Inventário de outubro')

    def test_gerente_muda_em_maos_pela_ficha(self):
        self.livro.with_user(self.gerente_com_ficha).write({'qty_available': 15})
        # A ficha grava o ajuste na RAIZ do armazém, não na prateleira: a
        # prateleira continua com 10 e a raiz ganha 15. É o core -- e é mais
        # um motivo para essa porta ser só do gerente (o manual avisa).
        Quant = self.env['stock.quant']
        self.assertEqual(Quant._get_available_quantity(
            self.livro, self.warehouse.lot_stock_id, strict=True), 15)
        self.assertEqual(Quant._get_available_quantity(
            self.livro, self.prateleira, strict=True), 10)

    def test_sudo_passa(self):
        """Fronteira aceita: código com sudo() aplica, como nas outras travas."""
        self._contar(self.assistente, 7)
        self._como(self.assistente).sudo()._apply_inventory()
        self.assertEqual(self.quant.quantity, 7)
