"""A estrela pela tela, no perfil de usuário de projeto: ★ e depois ★★."""
from odoo.tests import HttpCase, tagged

LOGIN = 'priority_star_tour'


@tagged('post_install', '-at_install')
class TestPriorityStarTour(HttpCase):

    def test_priority_star_tour(self):
        company = self.env.company
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Usuário de Projeto do Tour',
            'login': LOGIN,
            'password': LOGIN,
            'lang': 'en_US',
            'company_id': company.id,
            'company_ids': [(6, 0, company.ids)],
            'group_ids': [(4, self.env.ref('project.group_project_user').id)],
        })
        project = self.env['project.project'].create({
            'name': 'Pauta da Estrela', 'allow_priority_templates': True,
            'privacy_visibility': 'employees'})
        for name, priority in (('Modelo Uma', '1'), ('Modelo Duas', '2')):
            template = self.env['project.task'].create({
                'name': name, 'project_id': project.id, 'priority': priority})
            template.action_convert_to_template()
        task = self.env['project.task'].create({'name': 'Livro da Estrela', 'project_id': project.id})

        self.start_tour(f'/odoo/action-project.action_view_all_task/{task.id}',
                        'priority_star_tour', login=LOGIN)
        self.assertEqual(task.child_ids.mapped('name'), ['Modelo Duas'])
