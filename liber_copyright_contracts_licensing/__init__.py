# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """Show the licensing product IN the settings from day one.

    The code would fall back to the module's product anyway, but an empty
    field in Settings reads as "not configured" -- and that is what the
    first person to look at it saw. Fill every company that has none."""
    template = env.ref(
        "liber_copyright_contracts_licensing.product_rights_licensing",
        raise_if_not_found=False)
    if not template:
        return
    env["res.company"].sudo().search(
        [("contract_license_product_id", "=", False)]
    ).write({"contract_license_product_id": template.product_variant_id.id})
