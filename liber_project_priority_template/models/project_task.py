from markupsafe import Markup

from odoo import _, api, fields, models

# Writes the module does itself must not count as someone editing the card.
SYNC_CTX = 'priority_template_sync'


class ProjectTask(models.Model):
    _inherit = 'project.task'

    priority_template_source_id = fields.Many2one(
        'project.task', string='Created from template', copy=False, index='btree_not_null',
        ondelete='set null', readonly=True,
        help="The template card this sub-task was created from by the task's star.")
    priority_template_project_id = fields.Many2one(
        'project.project', string='Starred in project', index='btree_not_null', ondelete='cascade',
        help="On a template card: the project whose star creates this card as a sub-task. "
             "The card's own Project is where the sub-task is born.")
    priority_template_pristine = fields.Boolean(
        'Untouched since the star', copy=False, readonly=True,
        help="Created by the star and not touched since: changing the star may remove it.")

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        tasks.filtered(lambda t: t.priority not in (False, '0'))._sync_subtasks_with_priority()
        return tasks

    def write(self, vals):
        if not self.env.context.get(SYNC_CTX):
            touched = self.filtered('priority_template_pristine')
            if touched:
                touched.with_context(**{SYNC_CTX: True}).write({'priority_template_pristine': False})
        changed = self.browse()
        if 'priority' in vals and not self.env.context.get(SYNC_CTX):
            changed = self.filtered(lambda t: t.priority != vals['priority'])
        res = super().write(vals)
        if changed:
            changed._sync_subtasks_with_priority()
        return res

    def message_post(self, **kwargs):
        # A comment on a generated sub-task is work done: it stays.
        if kwargs.get('message_type', 'notification') == 'comment' and not self.env.context.get(SYNC_CTX):
            touched = self.filtered('priority_template_pristine')
            if touched:
                touched.with_context(**{SYNC_CTX: True}).write({'priority_template_pristine': False})
        return super().message_post(**kwargs)

    def action_convert_to_template(self):
        # A starred card got the star's sub-tasks the moment it was starred.
        # Becoming a template, it must not carry those copies inside (a
        # template that holds another template's copy is copied again, and so
        # on). The untouched ones go; the worked-on ones become plain content.
        for task in self:
            if not task.priority_template_project_id:
                # converted by hand: it serves the project it lives in
                task.with_context(**{SYNC_CTX: True}).priority_template_project_id = task.project_id
            generated = task.child_ids.filtered('priority_template_source_id')
            untouched = generated.filtered(lambda s: s._priority_template_untouched())
            untouched.with_context(**{SYNC_CTX: True}).unlink()
            rest = generated - untouched
            (rest | rest._get_all_subtasks()).with_context(**{SYNC_CTX: True}).write({
                'priority_template_source_id': False, 'priority_template_pristine': False})
        return super().action_convert_to_template()

    def _priority_template_untouched(self):
        """True when this generated sub-task and everything under it is still as created."""
        self.ensure_one()
        tree = self | self._get_all_subtasks()
        return all(tree.mapped('priority_template_pristine'))

    def _sync_subtasks_with_priority(self):
        """Make the task's generated sub-tasks follow its star.

        Each template card of the project with the task's star becomes one
        sub-task (with the sub-tasks it holds). Generated sub-tasks nobody
        touched since are removed when the star changes or goes away; touched
        ones are work done and stay. Sub-tasks made by hand are never touched,
        and a template already present is not copied again.
        """
        for task in self:
            if (task.parent_id or not task.project_id
                    or task.is_template or task.has_template_ancestor or task.has_project_template
                    or not task.project_id.allow_priority_templates):
                continue
            templates = task.project_id._get_priority_templates(task.priority)
            generated = task.child_ids.filtered('priority_template_source_id')
            removable = generated.filtered(
                lambda s: s.priority_template_source_id not in templates and s._priority_template_untouched())
            kept = generated.filtered(lambda s: s.priority_template_source_id not in templates) - removable
            removed_names = removable.mapped('name')
            removable.with_context(**{SYNC_CTX: True}).unlink()

            present = (generated - removable).priority_template_source_id
            created = self.browse()
            for template in templates - present:
                # born where the template says: another board, if so
                born_in = template.project_id or task.project_id
                default = {'parent_id': task.id, 'project_id': born_in.id, 'priority': '0'}
                if born_in in template.stage_id.project_ids:
                    default['stage_id'] = template.stage_id.id
                else:
                    # a column of another board would not show there: first column of born_in
                    default['stage_id'] = self.env['project.task.type'].search(
                        [('project_ids', '=', born_in.id)], limit=1).id
                sub = template.with_context(copy_from_template=True, **{SYNC_CTX: True}).copy(default)
                (sub | sub._get_all_subtasks()).with_context(**{SYNC_CTX: True}).write(
                    {'priority_template_pristine': True})
                sub.with_context(**{SYNC_CTX: True}).write({'priority_template_source_id': template.id})
                created |= sub
            task._note_priority_sync(templates, created, removed_names, kept)

    def _note_priority_sync(self, templates, created, removed_names, kept):
        self.ensure_one()
        stars = '★' * int(self.priority or 0)
        lines = []
        if created:
            lines.append(_('Sub-tasks created from the templates: %(names)s.',
                           names=', '.join(created.mapped('name'))))
        if removed_names:
            lines.append(_('Removed, untouched since the previous star: %(names)s.',
                           names=', '.join(removed_names)))
        if kept:
            lines.append(_('Kept, because they were already worked on: %(names)s.',
                           names=', '.join(kept.mapped('name'))))
        if stars and not templates:
            lines.append(_('%(stars)s: no template of this project has %(stars)s, so no sub-tasks were '
                           'created. Mark the star on a template card (Project settings → Task Templates).',
                           stars=stars))
        if lines:
            self.with_context(**{SYNC_CTX: True}).message_post(
                body=Markup('<br/>').join(lines), subtype_xmlid='mail.mt_note')
