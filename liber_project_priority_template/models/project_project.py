from odoo import _, fields, models

TEMPLATE_DOMAIN = [('is_template', '=', True), ('parent_id', '=', False)]


class ProjectProject(models.Model):
    _inherit = 'project.project'

    allow_priority_templates = fields.Boolean('Sub-tasks by Priority')

    def _get_priority_templates(self, priority):
        """The templates of this project starred like ``priority``, in list order.

        The star lives on the template card itself, and each such card becomes
        one sub-task of the starred task. A template belongs to the project
        whose star triggers it (``priority_template_project_id``); its own
        ``project_id`` is where the sub-task is born, which may be another board.
        """
        self.ensure_one()
        if not self.allow_priority_templates or priority not in ('1', '2', '3'):
            return self.env['project.task']
        return self.env['project.task'].search(
            TEMPLATE_DOMAIN + [('priority_template_project_id', '=', self.id), ('priority', '=', priority)],
            order='sequence, id')

    def action_open_priority_templates(self):
        """The templates of this project only: the list behind the settings link."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'liber_project_priority_template.action_task_templates')
        action['display_name'] = _('Task Templates: %(project)s', project=self.display_name)
        action['context'] = {'active_id': self.id, 'default_is_template': True,
                             'default_project_id': self.id,
                             'default_priority_template_project_id': self.id}
        return action
