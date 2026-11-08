from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProjectTaskTypeJob(models.Model):
    """One job of a column: the activity a task gets when it enters that column."""
    _name = 'project.task.type.job'
    _description = 'Column Job'
    _order = 'stage_id, sequence, id'

    stage_id = fields.Many2one('project.task.type', string='Column', required=True, ondelete='cascade',
                               index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Job', required=True, translate=False)
    activity_type_id = fields.Many2one(
        'mail.activity.type', string='Activity Type', required=True,
        default=lambda self: self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False),
        domain="['|', ('res_model', '=', False), ('res_model', '=', 'project.task')]")
    user_id = fields.Many2one(
        'res.users', string='Assignee',
        help="Who does the job. Empty: the task's own assignee (or whoever moved the card).")
    days = fields.Integer(
        'Days', default=0,
        help="The job is due this many days after production starts "
             "(the task's deadline minus the project's production time).")
    note = fields.Html('Script', sanitize_style=True,
                       help="Goes into the activity's note: how to do the job.")

    @api.constrains('days')
    def _check_days(self):
        for job in self.filtered(lambda j: j.days < 0):
            raise ValidationError(_('%(name)s: the days of a job cannot be negative.', name=job.name))
