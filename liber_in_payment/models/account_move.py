from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_invoice_in_payment_state(self):
        """Community hard-codes 'paid' here; Enterprise overrides it to
        'in_payment'. This house reconciles bank statements, so money still
        sitting on an outstanding account must show as pending — not as
        money in the bank.

        Two subtleties, both learned from the core:

        * The core also calls this hook on an EMPTY recordset as an edition
          detector (account.payment.create): answering 'in_payment' there
          would stop payments from getting their outstanding fallback and
          from generating journal entries. Empty recordset therefore keeps
          the Community answer, and payment creation is untouched.
        * The state is opt-out per company (companies sharing the database
          that never reconcile statements would stay 'in_payment' forever).
        """
        if self and all(m.company_id.use_in_payment_state for m in self):
            return 'in_payment'
        return super()._get_invoice_in_payment_state()
