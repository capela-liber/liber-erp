from odoo.tests import tagged
from odoo.tools.safe_eval import safe_eval
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestPriorityTemplate(TransactionCase):
    """Cada card-modelo com a estrela vira UMA subtarefa de quem ganha a estrela."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Stage = cls.env['project.task.type']
        cls.writer = new_test_user(cls.env, login='pt_writer', groups='project.group_project_user')
        cls.designer = new_test_user(cls.env, login='pt_designer', groups='project.group_project_user')

        cls.marketing = cls.env['project.project'].create({
            'name': 'Pauta', 'allow_priority_templates': True})
        cls.backlog = Stage.create({'name': 'Backlog', 'sequence': 1, 'project_ids': [cls.marketing.id]})
        cls.writing = Stage.create({'name': 'Redação', 'sequence': 2, 'project_ids': [cls.marketing.id]})
        cls.design = cls.env['project.project'].create({'name': 'Design'})

        cls.feira = cls._template('Evento em Feira Literária', '2', cls.writing, cls.writer, sequence=1)
        cls.livrarias = cls._template('Lançamento em livrarias', '2', cls.backlog, cls.designer, sequence=2)
        cls.eventos = cls._template('Eventos', '1', cls.backlog, cls.writer, sequence=3)

    @classmethod
    def _template(cls, name, priority, stage, user, project=None, sequence=10, inside=(), born_in=None):
        project = project or cls.marketing
        template = cls.env['project.task'].create({
            'name': name,
            'project_id': (born_in or project).id,
            'priority_template_project_id': project.id,
            'priority': priority,
            'sequence': sequence,
            'stage_id': stage.id if stage else False,
            'user_ids': [(6, 0, user.ids)],
            'child_ids': [(0, 0, {'name': n, 'project_id': project.id}) for n in inside],
        })
        template.action_convert_to_template()
        return template

    def _new_task(self, **vals):
        return self.env['project.task'].create({'name': 'Lançamento do livro X',
                                                'project_id': self.marketing.id, **vals})

    def _notes(self, task):
        return task.message_ids.filtered(
            lambda m: m.subtype_id == self.env.ref('mail.mt_note')).mapped('body')

    def _subtasks(self, task):
        return task.child_ids.sorted(lambda c: (c.sequence, c.id))

    def test_each_template_with_the_star_becomes_one_subtask(self):
        task = self._new_task()
        task.priority = '2'

        subs = self._subtasks(task)
        self.assertEqual(subs.mapped('name'), ['Evento em Feira Literária', 'Lançamento em livrarias'])
        feira, livrarias = subs
        self.assertEqual(feira.user_ids, self.writer)
        self.assertEqual(feira.stage_id, self.writing)
        self.assertEqual(livrarias.user_ids, self.designer)
        self.assertEqual(livrarias.stage_id, self.backlog)
        for sub in subs:
            self.assertEqual(sub.project_id, self.marketing)
            self.assertFalse(sub.is_template)
            self.assertFalse(sub.has_template_ancestor)
            self.assertEqual(sub.priority, '0')
        # the templates stay where they were
        self.assertTrue(self.feira.is_template and self.livrarias.is_template)
        self.assertTrue(any('Evento em Feira Literária' in n for n in self._notes(task)))

    def test_template_born_in_another_board(self):
        """O modelo é da Editoria, mas a subtarefa nasce no Design, na coluna do Design."""
        fila = self.env['project.task.type'].create({'name': 'Fila', 'project_ids': [self.design.id]})
        art = self._template('Arte das peças', '3', fila, self.designer, born_in=self.design)
        task = self._new_task(priority='3')
        sub = task.child_ids
        self.assertEqual(sub.name, 'Arte das peças')
        self.assertEqual(sub.project_id, self.design)
        self.assertEqual(sub.stage_id, fila)
        self.assertTrue(sub.display_in_project, "aparece no quadro do Design")
        # the template stays in the Editoria list, not in the Design one
        Task = self.env['project.task']
        for project, expected in ((self.marketing, True), (self.design, False)):
            action = project.action_open_priority_templates()
            domain = safe_eval(action['domain'], {'active_id': action['context']['active_id']})
            self.assertEqual(art in Task.search(domain), expected)
        # and it is swapped like any other
        task.priority = '0'
        self.assertFalse(task.child_ids)

    def test_moving_a_template_to_another_project_keeps_it_working(self):
        """Mudar o Projeto do modelo (o que foi feito no dev) não o tira da Editoria."""
        self.env['project.task.type'].create({'name': 'Fila do Design', 'project_ids': [self.design.id]})
        self.feira.project_id = self.design
        task = self._new_task(priority='2')
        feira = task.child_ids.filtered(lambda c: c.name == 'Evento em Feira Literária')
        self.assertEqual(feira.project_id, self.design)
        # its column was Editoria's: on the Design board it lands in Design's first column
        self.assertEqual(feira.stage_id, self.env['project.task.type'].search(
            [('project_ids', '=', self.design.id)], limit=1))

    def test_converting_by_hand_serves_its_own_project(self):
        card = self._new_task(name='Card comum')
        card.action_convert_to_template()
        self.assertEqual(card.priority_template_project_id, self.marketing)

    def test_star_on_the_template_decides(self):
        task = self._new_task(priority='1')
        self.assertEqual(task.child_ids.mapped('name'), ['Eventos'])

    def test_what_is_inside_a_template_comes_along(self):
        """Coerência: as subtarefas do modelo vêm junto, como netas da tarefa."""
        self._template('Com filhas', '3', self.backlog, self.writer, inside=['Filha A', 'Filha B'])
        task = self._new_task(priority='3')
        self.assertEqual(task.child_ids.mapped('name'), ['Com filhas'])
        grandchildren = task.child_ids.child_ids
        self.assertEqual(sorted(grandchildren.mapped('name')), ['Filha A', 'Filha B'])
        self.assertFalse(any(grandchildren.mapped('is_template')))
        self.assertFalse(any(grandchildren.mapped('has_template_ancestor')))
        self.assertEqual(grandchildren.project_id, self.marketing)
        # e as netas não disparam nada por conta própria
        self.assertFalse(grandchildren.child_ids)

    def test_template_of_another_project_is_ignored(self):
        self._template('Modelo do Design', '2', None, self.designer, project=self.design)
        task = self._new_task(priority='2')
        self.assertNotIn('Modelo do Design', task.child_ids.mapped('name'))

    def test_generated_subtasks_are_born_untouched(self):
        task = self._new_task(priority='2')
        self.assertTrue(all(task.child_ids.mapped('priority_template_pristine')))
        self.assertEqual(task.child_ids.priority_template_source_id, self.feira | self.livrarias)

    def test_one_star_then_two_swaps_untouched_subtasks(self):
        """★ → ★★: sai o que veio do ★ e ninguém mexeu, entra o do ★★."""
        task = self._new_task(priority='1')
        self.assertEqual(task.child_ids.mapped('name'), ['Eventos'])
        task.priority = '2'
        self.assertEqual(sorted(task.child_ids.mapped('name')),
                         ['Evento em Feira Literária', 'Lançamento em livrarias'])
        self.assertTrue(any('Removed' in n and 'Eventos' in n for n in self._notes(task)))

    def test_removing_the_star_removes_untouched_subtasks(self):
        task = self._new_task(priority='2')
        task.priority = '0'
        self.assertFalse(task.child_ids)

    def test_edited_subtask_is_work_done_and_stays(self):
        task = self._new_task(priority='1')
        task.child_ids.name = 'Eventos (já com data)'
        task.priority = '2'
        self.assertIn('Eventos (já com data)', task.child_ids.mapped('name'))
        self.assertEqual(len(task.child_ids), 3)
        self.assertTrue(any('Kept' in n and 'Eventos (já com data)' in n for n in self._notes(task)))

    def test_moving_a_subtask_to_another_column_is_work_done(self):
        task = self._new_task(priority='1')
        task.child_ids.stage_id = self.writing
        task.priority = '0'
        self.assertEqual(task.child_ids.mapped('name'), ['Eventos'])

    def test_commented_subtask_stays(self):
        task = self._new_task(priority='1')
        task.child_ids.message_post(body='Liguei para a livraria.', message_type='comment',
                                    subtype_xmlid='mail.mt_comment')
        task.priority = '0'
        self.assertEqual(task.child_ids.mapped('name'), ['Eventos'])

    def test_worked_on_grandchild_keeps_the_whole_block(self):
        self._template('Com filhas', '3', self.backlog, self.writer, inside=['Filha A'])
        task = self._new_task(priority='3')
        task.child_ids.child_ids.user_ids = self.designer
        task.priority = '0'
        self.assertEqual(task.child_ids.mapped('name'), ['Com filhas'])
        self.assertEqual(task.child_ids.child_ids.mapped('name'), ['Filha A'])

    def test_a_subtask_added_under_a_generated_one_keeps_it(self):
        task = self._new_task(priority='1')
        self.env['project.task'].create({'name': 'Minha', 'project_id': self.marketing.id,
                                         'parent_id': task.child_ids.id})
        task.priority = '0'
        self.assertEqual(task.child_ids.mapped('name'), ['Eventos'])

    def test_handmade_subtask_never_goes_and_does_not_block(self):
        task = self._new_task()
        self.env['project.task'].create({'name': 'Feita à mão', 'project_id': self.marketing.id,
                                         'parent_id': task.id})
        task.priority = '1'
        self.assertEqual(sorted(task.child_ids.mapped('name')), ['Eventos', 'Feita à mão'])
        task.priority = '0'
        self.assertEqual(task.child_ids.mapped('name'), ['Feita à mão'])

    def test_same_star_again_does_not_duplicate(self):
        task = self._new_task(priority='1')
        task.child_ids.name = 'Eventos editado'
        task.priority = '0'
        task.priority = '1'
        # the worked-on one stayed, and the template is not copied a second time
        self.assertEqual(task.child_ids.mapped('name'), ['Eventos editado'])

    def test_starred_card_turned_template_does_not_carry_the_copies(self):
        """Card ★★ ganha as subtarefas ★★; virando modelo, não as leva dentro."""
        card = self._new_task(priority='2')
        self.assertEqual(len(card.child_ids), 2)
        card.child_ids.filtered(lambda c: c.name == 'Lançamento em livrarias').name = 'Livrarias, editado'
        card.action_convert_to_template()
        self.assertEqual(card.child_ids.mapped('name'), ['Livrarias, editado'])
        self.assertFalse(card.child_ids.priority_template_source_id)
        # and copying it later brings only its own content
        task = self._new_task(priority='2')
        copy = task.child_ids.filtered(lambda c: c.name == card.name)
        self.assertEqual(copy.child_ids.mapped('name'), ['Livrarias, editado'])

    def test_star_without_template_leaves_a_note(self):
        task = self._new_task(priority='3')
        self.assertFalse(task.child_ids)
        self.assertTrue(any('★★★' in n and 'no template' in n for n in self._notes(task)))

    def test_option_off_does_nothing_and_says_nothing(self):
        self.marketing.allow_priority_templates = False
        task = self._new_task(priority='3')
        self.assertFalse(task.child_ids)
        self.assertFalse([n for n in self._notes(task) if '★' in n])

    def test_subtask_with_star_does_not_fire(self):
        parent = self._new_task()
        child = self.env['project.task'].create({'name': 'Filha', 'project_id': self.marketing.id,
                                                 'parent_id': parent.id})
        child.priority = '2'
        self.assertFalse(child.child_ids)

    def test_starring_a_template_does_not_fire(self):
        other = self._template('Outro modelo', '0', self.backlog, self.writer)
        other.priority = '2'
        self.assertFalse(other.child_ids)

    def test_project_user_can_star(self):
        """A plain project user (not manager) starring a card gets the sub-tasks."""
        self.marketing.privacy_visibility = 'employees'
        task = self._new_task().with_user(self.writer)
        task.priority = '2'
        self.assertEqual(len(task.child_ids), 2)
        task.priority = '1'   # swapping removes the untouched ones: needs unlink
        self.assertEqual(task.child_ids.mapped('name'), ['Eventos'])

    def test_settings_link_lists_only_this_projects_templates(self):
        self._template('Modelo do Design', '1', None, self.designer, project=self.design)
        action = self.marketing.action_open_priority_templates()
        # o domínio é o da ação gravada, avaliado com o active_id que o
        # endereço guarda -- é o que vale também ao recarregar a página
        domain = safe_eval(action['domain'], {'active_id': action['context']['active_id']})
        self.assertEqual(self.env['project.task'].search(domain),
                         self.feira | self.livrarias | self.eventos)
        self.assertEqual(action['context']['default_project_id'], self.marketing.id)

    def test_search_and_group_by_mother_task(self):
        """A subtarefa levada a outro board se acha pela mãe, por nome, e agrupa por ela."""
        task = self._new_task(priority='2')
        moved = task.child_ids[0]
        moved.project_id = self.design
        Task = self.env['project.task']
        found = Task.search([('project_id', '=', self.design.id),
                             ('parent_id.name', 'ilike', 'livro X')])
        self.assertEqual(found, moved)
        groups = Task._read_group([('project_id', '=', self.design.id)], ['parent_id'], ['__count'])
        self.assertEqual(groups, [(task, 1)])
        arch = Task.get_view(self.env.ref('project.view_task_search_form').id, 'search')['arch']
        self.assertIn('name="groupby_parent"', arch)
        self.assertIn("('parent_id.name', 'ilike', self)", arch)

    def test_no_menu(self):
        """Só o link nas Definições: nenhum menu para os modelos."""
        self.assertFalse(self.env['ir.ui.menu'].search(
            [('action', '=', 'ir.actions.act_window,%d' % self.env.ref(
                'liber_project_priority_template.action_task_templates').id)]))
