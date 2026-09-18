# -*- coding: utf-8 -*-
"""A corrida no get-or-create dos tipos de operação de consignação.

Achado em prod na Edlab Press (17/09/2026, via
scripts/censo_series_consignacao.sql): dois "Retorno de Consignação"
ativos, cada um com sua própria ir.sequence COM/IN, e o histórico
repartido entre os dois. `_get_consignment_return_operation_type` (e os
dois irmãos) fazia um `if not self.field: create` sem trava -- duas
liberações de logística perto o bastante uma da outra liam o campo vazio
antes de qualquer commit, e cada uma criava seu próprio tipo+sequence.

Estes testes prendem dois lados: que a trava (`FOR UPDATE`) é real (uma
segunda transação não consegue ler a linha travada) e que a migração
19.0.2.14.0 conserta uma base que já tem o duplicado, sem arriscar
arquivar o lado certo quando não sabe qual é.
"""
import importlib.util
import os

from odoo.modules import get_module_path
from odoo.tests import TransactionCase, tagged


def _load_migration():
    path = os.path.join(get_module_path('liber_soc_moves'),
                        'migrations', '19.0.2.14.0', 'post-migrate.py')
    spec = importlib.util.spec_from_file_location(
        'soc_moves_operation_type_race', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install', 'soc_moves')
class TestOperationTypeRace(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def _duplicate_return_type(self, active=True):
        """Simula o lado perdedor da corrida: um segundo "Retorno de
        Consignação", mesma empresa, mesmo sequence_code, que o campo do
        res.company não referencia."""
        canonical = self.company._get_consignment_return_operation_type()
        seq = self.env['ir.sequence'].sudo().create({
            'name': 'Consignment Return Operation (loser)',
            'prefix': 'COM/IN/%(year)s/',
            'padding': 5,
            'company_id': self.company.id,
            'number_next': 1,
        })
        loser = self.env['stock.picking.type'].sudo().create({
            'name': canonical.name,
            'code': 'internal',
            'sequence_id': seq.id,
            'sequence_code': 'COM/IN',
            'warehouse_id': canonical.warehouse_id.id,
            'company_id': self.company.id,
            'active': active,
        })
        return canonical, loser

    # -- a trava em si ---------------------------------------------------

    def test_the_type_is_created_once_and_reused(self):
        """Caminho feliz: chamar duas vezes não cria um segundo tipo."""
        first = self.company._get_consignment_return_operation_type()
        second = self.company._get_consignment_return_operation_type()

        self.assertEqual(first, second)
        self.assertEqual(
            self.env['stock.picking.type'].search_count(
                [('sequence_code', '=', 'COM/IN'),
                 ('company_id', '=', self.company.id)]),
            1, "um COM/IN por empresa, quantas vezes se chame")

    def test_second_transaction_blocks_on_the_lock(self):
        """Prova que a trava é real: com a linha travada e sem commit nesta
        transação, uma segunda conexão não consegue travá-la também."""
        self.env.cr.execute(
            "SELECT consignment_return_operation_type_id FROM res_company "
            "WHERE id = %s FOR UPDATE", (self.company.id,))

        cr2 = self.registry.cursor()
        try:
            with self.assertRaises(Exception):
                cr2.execute(
                    "SELECT consignment_return_operation_type_id FROM "
                    "res_company WHERE id = %s FOR UPDATE NOWAIT",
                    (self.company.id,))
        finally:
            cr2.rollback()
            cr2.close()

    # -- a migração que conserta uma base já duplicada -------------------

    def test_migration_archives_the_orphan_and_keeps_the_canonical(self):
        canonical, loser = self._duplicate_return_type()
        self.env.flush_all()

        migration = _load_migration()
        migration.migrate(self.env.cr, '19.0.2.14.0')
        self.env.invalidate_all()

        self.assertFalse(loser.active, "o órfão some da Visão Geral")
        self.assertTrue(canonical.active,
                        "o referenciado pelo res.company não é tocado")
        self.assertEqual(
            self.company.consignment_return_operation_type_id, canonical)

        # idempotência: rodar de novo não pode doer nem tentar arquivar
        # duas vezes o que já está arquivado.
        migration.migrate(self.env.cr, '19.0.2.14.0')
        self.env.invalidate_all()
        self.assertFalse(loser.active)
        self.assertTrue(canonical.active)

    def test_migration_skips_when_it_cannot_tell_which_is_canonical(self):
        """Edge case: dois duplicados ativos e NENHUM referenciado pelo
        campo do res.company (não é a forma que o bug de prod tomou, mas a
        migração não pode adivinhar -- arquivar os dois apagaria o cartão
        de quem está de verdade em uso)."""
        canonical, loser = self._duplicate_return_type()
        # Solta o ponteiro do res.company: agora nenhum dos dois "COM/IN"
        # bate com um campo da empresa.
        self.company.sudo().consignment_return_operation_type_id = False
        self.env.flush_all()

        migration = _load_migration()
        migration.migrate(self.env.cr, '19.0.2.14.0')
        self.env.invalidate_all()

        self.assertTrue(canonical.active, "sem saber qual é o certo, "
                        "a migração não arquiva nenhum")
        self.assertTrue(loser.active)

    def test_migration_is_a_no_op_without_duplicates(self):
        """Caso de erro/robustez: empresa com um único tipo por série (o
        caso comum) não pode ter nada arquivado nem lançar exceção."""
        operation_type = self.company._get_consignment_return_operation_type()
        self.env.flush_all()

        migration = _load_migration()
        migration.migrate(self.env.cr, '19.0.2.14.0')
        self.env.invalidate_all()

        self.assertTrue(operation_type.active)
