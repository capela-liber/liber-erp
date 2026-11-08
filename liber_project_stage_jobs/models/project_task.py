from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.tools import format_date

from .mail_activity import SYNC_CTX


class ProjectTask(models.Model):
    _inherit = 'project.task'

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        tasks.filtered('stage_id')._schedule_stage_jobs()
        return tasks

    def write(self, vals):
        moved = rescheduled = self.browse()
        if not self.env.context.get(SYNC_CTX):
            if 'stage_id' in vals:
                moved = self.filtered(lambda t: t.stage_id.id != vals['stage_id'])
            if 'date_deadline' in vals:
                rescheduled = self - moved
        res = super().write(vals)
        if moved:
            moved._schedule_stage_jobs()
        if rescheduled:
            rescheduled._reschedule_stage_jobs()
        return res

    def _stage_job_date(self, job):
        """When the job is due: start of production plus its days.

        Production starts the column's production period before the task's
        deadline. Without a deadline, the count starts today.
        """
        self.ensure_one()
        if self.date_deadline:
            start = fields.Datetime.context_timestamp(self, self.date_deadline).date() \
                - timedelta(days=job.stage_id.production_days)
        else:
            start = fields.Date.context_today(self)
        return start + timedelta(days=job.days)

    def _schedule_stage_jobs(self):
        """Schedule the jobs of the task's column as activities of the task.

        Each job of the column becomes one activity, due at the date counted
        from the task's deadline. A job whose activity is still open on the
        task is not scheduled again. Nothing is ever removed: leaving the
        column keeps the activities, which are work in progress.
        """
        for task in self:
            if task.parent_id or task.is_template or task.has_template_ancestor or task.has_project_template:
                continue
            jobs = task.stage_id.job_ids
            if not jobs:
                continue
            open_jobs = task.activity_ids.stage_job_id
            created = self.env['mail.activity']
            for job in jobs - open_jobs:
                user = job.user_id or task.user_ids[:1] or self.env.user
                created |= task.with_context(**{SYNC_CTX: True}).activity_schedule(
                    activity_type_id=job.activity_type_id.id,
                    summary=job.name, note=job.note or False,
                    date_deadline=task._stage_job_date(job), user_id=user.id,
                    stage_job_id=job.id, stage_job_pristine=True)
            if created:
                task._note_stage_jobs(created)

    def _reschedule_stage_jobs(self):
        """The deadline moved: untouched job activities follow it; touched ones keep their date."""
        for task in self:
            for activity in task.activity_ids.filtered(lambda a: a.stage_job_id and a.stage_job_pristine):
                activity.with_context(**{SYNC_CTX: True}).write(
                    {'date_deadline': task._stage_job_date(activity.stage_job_id)})

    def _note_stage_jobs(self, created):
        self.ensure_one()
        names = ', '.join(_('%(name)s (%(who)s, %(date)s)', name=a.summary, who=a.user_id.name,
                            date=format_date(self.env, a.date_deadline)) for a in created)
        lines = [_('Jobs of column %(column)s scheduled as activities: %(names)s.',
                   column=self.stage_id.display_name, names=names)]
        if not self.date_deadline:
            lines.append(_('The task has no deadline, so the jobs count from today. '
                           'Set the deadline and the untouched activities move to their dates.'))
        self.with_context(**{SYNC_CTX: True}).message_post(
            body=Markup('<br/>').join(lines), subtype_xmlid='mail.mt_note')
