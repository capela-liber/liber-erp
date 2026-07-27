# -*- coding: utf-8 -*-
"""O motor de plano: teto, posse, imutabilidade e a impressão do conteúdo.

Estes são os testes que decidem se o desenho vale: se qualquer um deles puder
falhar em produção, a separação entre propor e aplicar é decorativa.
"""

import json

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from ..tools import registry

TEST_TOOL = 'test.plan_partners'

# Registrada no import, como qualquer ferramenta real. O guard evita estourar
# se o módulo de teste for importado duas vezes na mesma sessão.
if TEST_TOOL not in registry.REGISTRY:

    @registry.tool(
        TEST_TOOL,
        kind=registry.KIND_PLAN,
        title='Propor contatos (teste)',
        description='Ferramenta de teste; propõe a criação de contatos.',
        writes=('res.partner',),
        input_schema={
            'type': 'object',
            'properties': {
                'names': {'type': 'array', 'items': {'type': 'string'}},
            },
            'required': ['names'],
            'additionalProperties': False,
        },
    )
    def _plan_partners(env, names):
        return {
            'summary': f'Criar {len(names)} contato(s).',
            'lines': [
                {
                    'operation': 'create',
                    'model': 'res.partner',
                    'values': {'name': name},
                    'summary': f'Criar o contato {name}',
                }
                for name in names
            ],
        }


@tagged('post_install', '-at_install')
class TestPlan(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['capela.ai.tool']._sync_from_registry()
        cls.tool = cls.env['capela.ai.tool'].search([('name', '=', TEST_TOOL)])

        cls.group = cls.env['res.groups'].create({
            'name': 'Capela AI — teste',
            'capela_ai_max_records': 2,
            'capela_ai_tool_ids': [(6, 0, cls.tool.ids)],
            'implied_ids': [(4, cls.env.ref('base.group_user').id)],
        })
        cls.user = cls.env['res.users'].create({
            'name': 'Pessoa do Teste',
            'login': 'capela_ai_test_plan',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id, cls.group.id])],
        })
        cls.outro = cls.env['res.users'].create({
            'name': 'Outra Pessoa',
            'login': 'capela_ai_test_plan_outro',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id, cls.group.id])],
        })
        cls.agent = cls.env['capela.ai.agent'].create({
            'name': 'Agente de Teste',
            'model_id': 'claude-opus-5',
            'tool_ids': [(6, 0, cls.tool.ids)],
            'group_ids': [(6, 0, [cls.group.id])],
        })

    def _propose(self, names, user=None):
        agent = self.agent.with_user(user or self.user)
        kind, plan = agent.execute_tool(TEST_TOOL, {'names': names})
        self.assertEqual(kind, registry.KIND_PLAN)
        return plan

    # -- o plano propõe e não grava ----------------------------------------

    def test_propor_nao_grava(self):
        antes = self.env['res.partner'].search_count([('name', '=', 'Fulano')])
        plan = self._propose(['Fulano'])
        self.assertEqual(plan.state, 'draft')
        self.assertEqual(
            self.env['res.partner'].search_count([('name', '=', 'Fulano')]), antes,
            "Propor não pode ter criado nada.",
        )

    def test_aprovar_grava(self):
        plan = self._propose(['Beltrano'])
        plan.with_user(self.user).action_approve()
        self.assertEqual(plan.state, 'applied')
        self.assertTrue(self.env['res.partner'].search([('name', '=', 'Beltrano')]))

    # -- o teto do nível ----------------------------------------------------

    def test_teto_do_nivel_recusa_plano_grande(self):
        """O grupo do teste concede 2; três documentos não passam."""
        with self.assertRaises(UserError):
            self._propose(['Um', 'Dois', 'Três'])

    def test_sem_concessao_nao_ha_agente(self):
        sem_grupo = self.env['res.users'].create({
            'name': 'Sem Concessão',
            'login': 'capela_ai_test_sem',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        with self.assertRaises(AccessError):
            self.agent.with_user(sem_grupo).execute_tool(TEST_TOOL, {'names': ['X']})

    # -- posse: só quem pediu aprova ---------------------------------------

    def test_outra_pessoa_nao_aprova(self):
        plan = self._propose(['Sicrano'])
        with self.assertRaises(AccessError):
            plan.with_user(self.outro).action_approve()

    def test_nao_aplica_duas_vezes(self):
        plan = self._propose(['Duplicado'])
        plan.with_user(self.user).action_approve()
        with self.assertRaises(UserError):
            plan.with_user(self.user).action_approve()

    # -- a impressão do conteúdo -------------------------------------------

    def test_conteudo_alterado_nao_aplica(self):
        """Simula adulteração no banco: o hash não bate e o plano não roda."""
        plan = self._propose(['Original'])
        line = plan.line_ids[0]
        line.sudo().write({
            'values_json': json.dumps({'name': 'Adulterado'}, sort_keys=True),
        })
        with self.assertRaises(UserError):
            plan.with_user(self.user).action_approve()
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Adulterado')]))

    def test_linha_e_imutavel_para_gente(self):
        plan = self._propose(['Imutável'])
        with self.assertRaises(ValidationError):
            plan.line_ids[0].with_user(self.user).write({'summary': 'outra coisa'})

    # -- o que não é exprimível --------------------------------------------

    def test_unlink_nao_e_operacao(self):
        tool_def = registry.get(TEST_TOOL)
        with self.assertRaises(UserError):
            self.env['capela.ai.plan'].with_user(self.user)._check_line(
                tool_def,
                {'operation': 'unlink', 'model': 'res.partner', 'res_id': 1,
                 'values': {'x': 1}, 'summary': 'apagar'},
                1,
            )

    def test_modelo_fora_da_declaracao_nao_passa(self):
        tool_def = registry.get(TEST_TOOL)
        with self.assertRaises(UserError):
            self.env['capela.ai.plan'].with_user(self.user)._check_line(
                tool_def,
                {'operation': 'create', 'model': 'res.country',
                 'values': {'name': 'Atlântida'}, 'summary': 'criar país'},
                1,
            )

    def test_operacao_sem_explicacao_nao_passa(self):
        """Um plano que um humano não consegue ler não é um plano."""
        tool_def = registry.get(TEST_TOOL)
        with self.assertRaises(UserError):
            self.env['capela.ai.plan'].with_user(self.user)._check_line(
                tool_def,
                {'operation': 'create', 'model': 'res.partner',
                 'values': {'name': 'Anônimo'}, 'summary': ''},
                1,
            )

    # -- a interseção tripla -----------------------------------------------

    def test_ferramenta_nao_concedida_some_do_catalogo(self):
        """Tirar do grupo tira da lista que o modelo sequer enxerga."""
        self.group.capela_ai_tool_ids = [(5, 0, 0)]
        schemas = self.agent.with_user(self.user).api_tool_schemas()
        self.assertEqual(schemas, [])
        with self.assertRaises(AccessError):
            self.agent.with_user(self.user).execute_tool(TEST_TOOL, {'names': ['X']})

    def test_agente_fora_do_alcance_do_grupo(self):
        self.agent.group_ids = [(5, 0, 0)]
        with self.assertRaises(AccessError):
            self.agent.with_user(self.user).execute_tool(TEST_TOOL, {'names': ['X']})
