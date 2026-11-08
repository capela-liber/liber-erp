"""O tour das Subtarefas por prioridade: a opção, os modelos e o menu, pela tela."""
from odoo.tests import HttpCase, tagged

LOGIN = 'priority_template_tour'


@tagged('post_install', '-at_install')
class TestPriorityTemplateTour(HttpCase):

    def test_priority_template_tour(self):
        company = self.env.company
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gerente de Projeto do Tour',
            'login': LOGIN,
            'password': LOGIN,
            'lang': 'en_US',
            'company_id': company.id,
            'company_ids': [(6, 0, company.ids)],
            'group_ids': [(4, self.env.ref('project.group_project_manager').id)],
        })
        project = self.env['project.project'].create({'name': 'Pauta do Tour'})
        design = self.env['project.project'].create({'name': 'Design do Tour'})
        template = self.env['project.task'].create({
            'name': 'Evento em Livraria',
            'project_id': project.id,
            'priority': '2',
        })
        template.action_convert_to_template()
        # o modelo de outro projeto não pode aparecer na lista deste
        alheio = self.env['project.task'].create({'name': 'Modelo do Design', 'project_id': design.id})
        alheio.action_convert_to_template()

        self.start_tour(f'/odoo/action-project.open_view_project_all_config/{project.id}',
                        'priority_template_tour', login=LOGIN)
        self.assertTrue(project.allow_priority_templates)

