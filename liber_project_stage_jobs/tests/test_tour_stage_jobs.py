"""A coluna pela tela, no perfil de usuário de projeto: Produção e depois Feito."""
from odoo.tests import HttpCase, tagged

LOGIN = 'stage_jobs_tour'


@tagged('post_install', '-at_install')
class TestStageJobsTour(HttpCase):

    def test_stage_jobs_tour(self):
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
            'name': 'Editoria do Tour', 'privacy_visibility': 'employees'})
        Stage = self.env['project.task.type']
        ideias = Stage.create({'name': 'Ideias', 'sequence': 1, 'project_ids': [project.id]})
        Stage.create({'name': 'Producao', 'sequence': 2, 'project_ids': [project.id], 'production_days': 60,
                      'job_ids': [(0, 0, {'name': 'Capa', 'days': 20})]})
        Stage.create({'name': 'Feito', 'sequence': 3, 'project_ids': [project.id]})
        task = self.env['project.task'].create({
            'name': 'Livro do Tour', 'project_id': project.id, 'stage_id': ideias.id,
            'date_deadline': '2027-03-30 12:00:00'})

        self.start_tour(f'/odoo/action-project.action_view_all_task/{task.id}',
                        'stage_jobs_tour', login=LOGIN)
        self.assertEqual(task.activity_ids.mapped('summary'), ['Capa'])
        self.assertEqual(str(task.activity_ids.date_deadline), '2027-02-18')
