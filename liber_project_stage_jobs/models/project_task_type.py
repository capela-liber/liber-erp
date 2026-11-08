from odoo import fields, models


class ProjectTaskType(models.Model):
    _inherit = 'project.task.type'

    job_ids = fields.One2many('project.task.type.job', 'stage_id', string='Jobs', copy=True)
    production_days = fields.Integer(
        'Production Period (days)', default=60,
        help="Number of days counted back from the task's deadline to the start of production: "
             "the jobs of this column are due that start plus their days.")
    job_count = fields.Integer(compute='_compute_job_count')

    def _compute_job_count(self):
        for stage in self:
            stage.job_count = len(stage.job_ids)
