from odoo import models
from odoo.tools import SQL


class AccountAccount(models.Model):
    _inherit = 'account.account'

    def _field_to_sql(self, alias: str, field_expr: str, query=None) -> SQL:
        """Express the non-stored ``group_id`` in SQL.

        ``account.account.group_id`` is a compute without ``store``, so the ORM
        refuses to put it in a WHERE or a GROUP BY ("Cannot convert
        account.account.group_id to SQL because it is not stored"), which is
        exactly what the search panel needs.

        The core solves the same problem for ``root_id`` by mapping it to
        ``SUBSTRING(code, 1, 2)`` here.  We do the same for ``group_id``, with
        the very query ``_compute_account_group`` runs: the deepest
        ``account.group`` of the active root company whose prefix range covers
        the account code.  Nothing is stored, so nothing ever needs recomputing.
        """
        if field_expr == 'group_id':
            return SQL(
                """(
                    SELECT account_group.id
                      FROM account_group
                     WHERE account_group.company_id = %(root_company_id)s
                       AND account_group.code_prefix_start <= LEFT(%(code)s, char_length(account_group.code_prefix_start))
                       AND account_group.code_prefix_end >= LEFT(%(code)s, char_length(account_group.code_prefix_end))
                  ORDER BY char_length(account_group.code_prefix_start) DESC, account_group.id
                     LIMIT 1
                )""",
                code=self._field_to_sql(alias, 'code', query),
                root_company_id=self.env.company.root_id.id,
            )
        return super()._field_to_sql(alias, field_expr, query)
