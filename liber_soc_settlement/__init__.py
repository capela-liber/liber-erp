# -*- coding: utf-8 -*-
from . import models
from . import wizards


def post_init_rename_channels(env):
    """Rename the old shared feed. A noupdate="1" record is never touched by an
    upgrade -- which is what protects its history, and also what means the new
    name in the XML would never reach it."""
    channel = env.ref('liber_soc_settlement.channel_consignment_replies',
                      raise_if_not_found=False)
    if channel and channel.name != 'Consignação / Operações':
        channel.name = 'Consignação / Operações'


def post_init_backfill_campaign_codes(env):
    """Give a code to the campaigns that existed before codes did.

    This cannot live in the model's init(): init() runs while the tables are set
    up, BEFORE the data files are loaded -- so the sequence does not exist yet and
    every code would come out as the fallback "/". Ask me how I know.

    active_test=False on purpose: an archived campaign is exactly the one whose
    name is ambiguous with a live one (this base has two "Orides"), so it needs
    the code the most.
    """
    post_init_rename_channels(env)
    Campaign = env['consignment.template'].with_context(active_test=False)
    for campaign in Campaign.search(
            ['|', ('code', '=', False), ('code', '=', '/')], order='id'):
        campaign.code = env['ir.sequence'].next_by_code('consignment.campaign')
