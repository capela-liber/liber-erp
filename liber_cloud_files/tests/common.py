# -*- coding: utf-8 -*-
"""The gate suite, written once and run by every provider.

The question these tests ask is the one the house asks: *can someone who
was not granted write actually write?* Not "does the button hide" -- the
screen is the last line, not the first. Whoever holds a session can call
the ORM, so the answer has to hold at the model.

Two powers get confused and must not be: seeing a shelf and filling it.
A provider's Manager is trusted with the first over the whole provider,
and with the second nowhere in particular -- filling a folder is decided
folder by folder, on that folder's own write ACL, Manager or not.

A provider module runs it in three lines::

    class TestGithubGate(CloudGateCase):
        PROVIDER = 'github'
        ACCOUNT_VALS = {'github_token': 't'}
        MODULE = 'liber_github'
"""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class CloudGateCase(TransactionCase):
    """Subclass and set PROVIDER, ACCOUNT_VALS and MODULE.

    The base itself is not imported by the chassis' tests/__init__, so it
    never runs headless: with PROVIDER unset there is no shelf to test.
    """
    PROVIDER = None
    ACCOUNT_VALS = {}
    MODULE = None

    # Odoo's loader collects only the test methods a class declares in its
    # own __dict__; a subclass that inherits every test would be gathered
    # and then run nothing at all -- silently, with the suite still green.
    # This flag is the framework's own way of asking for inherited ones.
    allow_inherited_tests_method = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not cls.PROVIDER:
            cls.skipTest(cls, "base class: no provider to test")
        cls.company = cls.env.company
        Account = cls.env['liber.cloud.account']
        cls.account = Account.search([
            ('provider', '=', cls.PROVIDER),
            ('company_id', '=', cls.company.id)], limit=1) or Account.create(
                dict(cls.ACCOUNT_VALS, provider=cls.PROVIDER,
                     company_id=cls.company.id))

        # The roles: the folder ACL is written in terms of these, exactly
        # as Marketing and Editorial are in the real database.
        cls.role_reads = cls.env['res.groups'].create(
            {'name': 'Gate role: reads'})
        cls.role_writes = cls.env['res.groups'].create(
            {'name': 'Gate role: writes'})

        cls.folder = cls.env['liber.cloud.folder'].create({
            'name': 'Gate folder', 'provider': cls.PROVIDER,
            'path': '/gate/%s' % cls.PROVIDER,
            'external_id': 'edlab/gate',
            'read_group_ids': [(4, cls.role_reads.id)],
            'write_group_ids': [(4, cls.role_writes.id)],
        })
        cls.file = cls.env['liber.cloud.file'].create({
            'folder_id': cls.folder.id, 'name': 'gate.pdf',
            'path': '/gate/%s/gate.pdf' % cls.PROVIDER,
        })

        def _user(login, group, role=None):
            user = new_test_user(
                cls.env, '%s_%s' % (cls.PROVIDER, login),
                groups='base.group_user,%s.%s' % (cls.MODULE, group))
            if role:
                user.group_ids += role
            return user

        # The four shapes a person takes in this house.
        cls.reader = _user('reader', 'group_liber_%s_user' % cls.PROVIDER,
                           cls.role_reads)
        cls.writer = _user('writer', 'group_liber_%s_user' % cls.PROVIDER,
                           cls.role_writes)
        cls.manager = _user('manager', 'group_liber_%s_manager' % cls.PROVIDER)
        cls.manager_writer = _user(
            'manager_writer', 'group_liber_%s_manager' % cls.PROVIDER,
            cls.role_writes)

    def _as(self, user):
        """Read the record fresh as `user`.

        Without invalidating, the cache filled by the previous user
        answers for the next one and the sweep measures a single person
        four times over.
        """
        self.env.invalidate_all()
        return self.file.with_user(user)

    # ------------------------------------------------------------------
    # writing the ledger
    # ------------------------------------------------------------------
    def test_manager_without_write_acl_cannot_edit_the_record(self):
        """Being Manager of the provider is not being granted the folder.

        Configuring the shelf is one power; filling it is another. The
        Manager reads every folder of their provider on purpose -- and
        that must not spill into writing on records of a folder whose
        write ACL never named them.
        """
        with self.assertRaises(AccessError):
            self._as(self.manager).write({'name': 'renamed by manager'})

    def test_manager_without_write_acl_cannot_delete_the_record(self):
        with self.assertRaises(AccessError):
            self._as(self.manager).unlink()

    def test_reader_cannot_edit_the_record(self):
        with self.assertRaises(AccessError):
            self._as(self.reader).write({'name': 'renamed by reader'})

    def test_write_acl_is_what_grants_the_edit(self):
        """And the same ACL, held by a plain User or by a Manager, does."""
        self._as(self.writer).write({'name': 'renamed by writer'})
        self.assertEqual(self.file.name, 'renamed by writer')
        self._as(self.manager_writer).write({'name': 'renamed by manager+acl'})
        self.assertEqual(self.file.name, 'renamed by manager+acl')

    # ------------------------------------------------------------------
    # the gate before the provider
    # ------------------------------------------------------------------
    def test_gate_refuses_write_to_everyone_but_the_write_acl(self):
        for user in (self.reader, self.manager):
            self.env.invalidate_all()
            with self.assertRaises(AccessError):
                self.folder.with_user(user)._ensure_access('write')
        for user in (self.writer, self.manager_writer):
            self.env.invalidate_all()
            self.folder.with_user(user)._ensure_access('write')

    # A test for the Upload button agreeing with the gate belongs here too,
    # and is deliberately absent: `can_upload` is still uncommitted work on
    # the wizard, and a suite that reaches for a field its own commit does
    # not carry would fail wherever it lands first. It goes in with that
    # field, not before it.
