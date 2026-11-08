from datetime import date, datetime

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestStageJobs(TransactionCase):
    """Cada job da coluna vira UMA atividade de quem entra nela, com a data
    contada do Prazo final: −tempo de produção + dias do job."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Stage = cls.env['project.task.type']
        cls.designer = new_test_user(cls.env, login='sj_designer', groups='project.group_project_user')
        cls.reviewer = new_test_user(cls.env, login='sj_reviewer', groups='project.group_project_user')
        cls.editor = new_test_user(cls.env, login='sj_editor', groups='project.group_project_user')
        cls.todo = cls.env.ref('mail.mail_activity_data_todo')
        cls.call = cls.env.ref('mail.mail_activity_data_call')

        cls.editoria = cls.env['project.project'].create({'name': 'Editoria'})
        cls.ideias = Stage.create({'name': 'Ideias', 'sequence': 1, 'project_ids': [cls.editoria.id]})
        cls.producao = Stage.create({
            'name': 'Produção', 'sequence': 2, 'project_ids': [cls.editoria.id], 'production_days': 60,
            'job_ids': [
                (0, 0, {'name': 'Capa', 'days': 20, 'user_id': cls.designer.id, 'sequence': 1,
                        'note': '<p>Pedir a arte ao designer.</p>'}),
                (0, 0, {'name': 'Revisão de provas', 'days': 35, 'user_id': cls.reviewer.id, 'sequence': 2,
                        'activity_type_id': cls.call.id}),
                (0, 0, {'name': 'Checagem de fechamento', 'days': 55, 'sequence': 3}),
            ]})
        cls.prelo = Stage.create({
            'name': 'Prelo', 'sequence': 3, 'project_ids': [cls.editoria.id],
            'job_ids': [(0, 0, {'name': 'Ficha ao gráfico', 'days': 60, 'user_id': cls.reviewer.id})]})
        cls.feito = Stage.create({'name': 'Feito', 'sequence': 4, 'project_ids': [cls.editoria.id]})
        cls.capa, cls.revisao, cls.checagem = cls.producao.job_ids.sorted('sequence')

    def _new_task(self, **vals):
        return self.env['project.task'].with_user(self.editor).create({
            'name': 'Livro X', 'project_id': self.editoria.id, 'stage_id': self.ideias.id,
            'date_deadline': datetime(2027, 3, 30, 12, 0), 'user_ids': [(6, 0, self.editor.ids)], **vals})

    def _notes(self, task):
        return task.message_ids.filtered(
            lambda m: m.subtype_id == self.env.ref('mail.mt_note')).mapped('body')

    def _acts(self, task):
        return task.activity_ids.sorted(lambda a: (a.date_deadline, a.id))

    # caminho feliz ------------------------------------------------------------

    def test_entering_the_column_schedules_the_jobs_dated_from_the_deadline(self):
        task = self._new_task()
        self.assertFalse(task.activity_ids)

        task.stage_id = self.producao

        capa, revisao, checagem = self._acts(task)
        self.assertEqual(capa.summary, 'Capa')
        # início da produção = 30/03 − 60 = 29/01; capa em 20 dias, revisão em 35, checagem em 55
        self.assertEqual(capa.date_deadline, date(2027, 2, 18))
        self.assertEqual(revisao.date_deadline, date(2027, 3, 5))
        self.assertEqual(checagem.date_deadline, date(2027, 3, 25))
        # a atividade leva o que o job diz: responsável, tipo e roteiro na nota
        self.assertEqual(capa.user_id, self.designer)
        self.assertIn('Pedir a arte', capa.note)
        self.assertEqual(revisao.activity_type_id, self.call)
        self.assertEqual(capa.activity_type_id, self.todo)
        # job sem responsável: o responsável do card
        self.assertEqual(checagem.user_id, self.editor)
        self.assertEqual(capa.stage_job_id, self.capa)
        self.assertTrue(capa.stage_job_pristine)
        note = self._notes(task)[0]
        self.assertIn('Capa', note)
        self.assertIn('02/18/2027', note)

    def test_created_in_the_column_schedules_too(self):
        task = self._new_task(stage_id=self.producao.id)
        self.assertEqual(len(task.activity_ids), 3)

    def test_leaving_the_column_removes_nothing_and_the_next_column_adds_its_own(self):
        task = self._new_task(stage_id=self.producao.id)
        task.stage_id = self.prelo
        self.assertEqual(set(task.activity_ids.mapped('summary')),
                         {'Capa', 'Revisão de provas', 'Checagem de fechamento', 'Ficha ao gráfico'})
        self.assertEqual(task.activity_ids.filtered(lambda a: a.summary == 'Ficha ao gráfico').date_deadline,
                         date(2027, 3, 30))
        task.stage_id = self.feito
        self.assertEqual(len(task.activity_ids), 4)
        self.assertEqual(len(self._notes(task)), 2)  # Produção e Prelo; Feito cala

    def test_coming_back_does_not_duplicate_open_jobs_but_reschedules_done_ones(self):
        task = self._new_task(stage_id=self.producao.id)
        capa = task.activity_ids.filtered(lambda a: a.summary == 'Capa')
        capa.with_user(self.designer).action_done()
        task.stage_id = self.feito
        task.stage_id = self.producao
        self.assertEqual(sorted(task.activity_ids.mapped('summary')),
                         ['Capa', 'Checagem de fechamento', 'Revisão de provas'])
        self.assertEqual(len(task.activity_ids), 3)

    # o prazo --------------------------------------------------------------------

    def test_without_deadline_the_jobs_count_from_today_until_it_is_set(self):
        task = self._new_task(date_deadline=False, stage_id=self.producao.id)
        capa, revisao, _checagem = self._acts(task)
        today = date.today()
        self.assertEqual((capa.date_deadline - today).days, 20)
        self.assertIn('no deadline', self._notes(task)[0])

        revisao.with_user(self.reviewer).write({'date_deadline': date(2027, 1, 1)})
        task.date_deadline = datetime(2027, 3, 30, 12, 0)

        self.assertEqual(capa.date_deadline, date(2027, 2, 18))
        self.assertEqual(revisao.date_deadline, date(2027, 1, 1))
        self.assertFalse(revisao.stage_job_pristine)

    def test_moving_the_deadline_moves_the_untouched_activities(self):
        task = self._new_task(stage_id=self.producao.id)
        capa, revisao, _checagem = self._acts(task)
        revisao.with_user(self.reviewer).write({'user_id': self.editor.id})
        task.date_deadline = datetime(2027, 4, 29, 12, 0)
        self.assertEqual(capa.date_deadline, date(2027, 3, 20))
        self.assertEqual(revisao.date_deadline, date(2027, 3, 5))

    def test_production_period_is_the_columns(self):
        self.assertEqual(self.prelo.production_days, 60)  # o padrão da coluna
        self.producao.production_days = 30
        task = self._new_task(stage_id=self.producao.id)
        capa = self._acts(task)[0]
        self.assertEqual(capa.date_deadline, date(2027, 3, 20))  # 30/03 − 30 + 20

        self.prelo.production_days = 10
        task.stage_id = self.prelo
        ficha = task.activity_ids.filtered(lambda a: a.summary == 'Ficha ao gráfico')
        self.assertEqual(ficha.date_deadline, date(2027, 5, 19))  # 30/03 − 10 + 60
        # e o reagendamento respeita o período de cada coluna
        task.date_deadline = datetime(2027, 4, 29, 12, 0)
        self.assertEqual(capa.date_deadline, date(2027, 4, 19))
        self.assertEqual(ficha.date_deadline, date(2027, 6, 18))

    # limites --------------------------------------------------------------------

    def test_column_without_jobs_does_nothing(self):
        task = self._new_task(stage_id=self.feito.id)
        self.assertFalse(task.activity_ids)
        self.assertFalse(self._notes(task))

    def test_templates_and_subtasks_do_not_trigger(self):
        template = self.env['project.task'].create({
            'name': 'Modelo', 'project_id': self.editoria.id, 'stage_id': self.ideias.id})
        template.action_convert_to_template()
        template.stage_id = self.producao
        self.assertFalse(template.activity_ids)
        task = self._new_task()
        sub = self.env['project.task'].create({'name': 'Orelha', 'parent_id': task.id,
                                               'project_id': self.editoria.id, 'stage_id': self.producao.id})
        self.assertFalse(sub.activity_ids)

    def test_negative_days_are_refused(self):
        with self.assertRaises(ValidationError):
            self.capa.days = -1

    def test_project_user_edits_the_columns_jobs_and_a_plain_user_only_reads(self):
        job = self.env['project.task.type.job'].with_user(self.editor).create({
            'stage_id': self.prelo.id, 'name': 'Prova de cor', 'days': 50})
        job.with_user(self.editor).write({'days': 52})
        self.assertEqual(self.prelo.job_ids.mapped('name'), ['Ficha ao gráfico', 'Prova de cor'])
        plain = new_test_user(self.env, login='sj_plain', groups='base.group_user')
        self.assertTrue(job.with_user(plain).read(['name']))
        with self.assertRaises(AccessError):
            job.with_user(plain).write({'days': 1})
        job.with_user(self.editor).unlink()

    def test_deleting_the_column_job_keeps_the_activity(self):
        task = self._new_task(stage_id=self.producao.id)
        capa = task.activity_ids.filtered(lambda a: a.summary == 'Capa')
        self.capa.unlink()
        self.assertTrue(capa.exists())
        self.assertFalse(capa.stage_job_id)
