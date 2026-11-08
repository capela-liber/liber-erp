from odoo import fields, models

# Writes the module does itself must not count as someone editing the activity.
SYNC_CTX = 'stage_job_sync'
# Changing any of these by hand makes the activity "touched": the deadline no longer moves it.
TOUCH_FIELDS = {'date_deadline', 'user_id', 'note', 'summary', 'activity_type_id'}


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    stage_job_id = fields.Many2one(
        'project.task.type.job', string='Column job', ondelete='set null', index='btree_not_null',
        readonly=True, help="The job of the column this activity was scheduled from.")
    stage_job_pristine = fields.Boolean(
        'Untouched since scheduled', readonly=True,
        help="Scheduled by the column and not edited since: a new deadline on the task moves it.")

    def write(self, vals):
        if (not self.env.context.get(SYNC_CTX) and TOUCH_FIELDS & set(vals)
                and any(self.mapped('stage_job_pristine'))):
            vals = dict(vals, stage_job_pristine=False)
        return super().write(vals)
