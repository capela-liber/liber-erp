"""Tarefa-mãe na busca, pela tela, num board que não é o da mãe."""
from odoo.tests import HttpCase, tagged

LOGIN = 'mother_task_tour'


@tagged('post_install', '-at_install')
class TestMotherTaskTour(HttpCase):

    def test_mother_task_tour(self):
        company = self.env.company
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Designer do Tour',
            'login': LOGIN,
            'password': LOGIN,
            'lang': 'en_US',
            'company_id': company.id,
            'company_ids': [(6, 0, company.ids)],
            'group_ids': [(4, self.env.ref('project.group_project_user').id)],
        })
        Project = self.env['project.project']
        editoria = Project.create({'name': 'Editoria do Tour', 'privacy_visibility': 'employees'})
        design = Project.create({'name': 'Design do Tour', 'privacy_visibility': 'employees'})
        self.env['project.task.type'].create({'name': 'Fila', 'project_ids': [design.id]})
        Task = self.env['project.task']
        for mae, filha in (('Livro da Mãe', 'Arte do livro'), ('Outro livro', 'Arte de outro livro')):
            parent = Task.create({'name': mae, 'project_id': editoria.id})
            Task.create({'name': filha, 'project_id': design.id, 'parent_id': parent.id})

        self.start_tour(f'/odoo/project/{design.id}/tasks', 'mother_task_tour', login=LOGIN)
