# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    soc_sales_window_months = fields.Integer(
        string='Sales analysis window (months)', default=3,
        config_parameter='soc_settlement.sales_window_months',
        help="Number of months used to total the recent sales of a title "
             "(reported quantities across settled settlements) shown in the "
             "settlement analysis column.")
    consignment_map_text = fields.Html(
        related='company_id.consignment_map_text', readonly=False)
    consignment_settlement_operation_type_id = fields.Many2one(
        'stock.picking.type',
        related='company_id.consignment_settlement_operation_type_id',
        readonly=False)

    # --- Return dunning (CR chasing) ------------------------------------
    # One master variable (the tolerable window) + three checkpoints expressed
    # as a PERCENTAGE of it. Change the days and the calendar reflows; the
    # ladder is driven off these by the nightly cron (_cron_return_dunning).
    return_dunning_enabled = fields.Boolean(
        string='Chase pending returns', default=True,
        config_parameter='soc_settlement.return_dunning_enabled',
        help="Master switch: when off, the nightly cron does nothing and no "
             "return-request e-mails, calls, alerts or escalations are fired.")
    return_sla_days = fields.Integer(
        string='Tolerable return window (days)', default=30,
        config_parameter='soc_settlement.return_sla_days',
        help="How long a customer may take to send merchandise back before the "
             "return (CR) is considered overdue. The dunning checkpoints below "
             "are computed as a percentage of this window.")
    return_nudge_pct = fields.Integer(
        string='Nudge at (% of window)', default=25,
        config_parameter='soc_settlement.return_nudge_pct',
        help="When no return has happened by this share of the window, e-mail "
             "the return request (CR) again and schedule a call for the "
             "responsible. Default 25% (~day 7 of 30).")
    return_call_pct = fields.Integer(
        string='Call due at (% of window)', default=40,
        config_parameter='soc_settlement.return_call_pct',
        help="Deadline of the 'call the customer' activity scheduled at the "
             "nudge. Default 40% (~day 12 of 30).")
    return_broadcast_pct = fields.Integer(
        string='Broadcast at (% of window)', default=65,
        config_parameter='soc_settlement.return_broadcast_pct',
        help="Still no return by this point posts a red alert in the "
             "'Consignação — Respostas' channel so the whole team sees it. "
             "Default 65% (~day 20 of 30). At 100% it escalates to the manager.")
    return_escalation_manager_id = fields.Many2one(
        'res.users', related='company_id.return_escalation_manager_id',
        readonly=False)
    return_request_text = fields.Html(
        related='company_id.return_request_text', readonly=False)

    # --- Consigned-title health (days since the title's last settlement) -----
    # One tag per map line: Ok -> Attention -> Critical -> No Return, by how long
    # since this book last settled (acerto) for this customer.
    shelf_ok_days = fields.Integer(
        string='Ok up to (days)', default=45,
        config_parameter='soc_settlement.shelf_ok_days',
        help="A consigned title settled within this many days is Ok (green).")
    shelf_attention_days = fields.Integer(
        string='Attention up to (days)', default=60,
        config_parameter='soc_settlement.shelf_attention_days',
        help="Past the healthy window and up to here -> Attention (yellow). "
             "Default 60 (~2 months).")
    shelf_critical_days = fields.Integer(
        string='Critical up to (days)', default=120,
        config_parameter='soc_settlement.shelf_critical_days',
        help="Up to here -> Critical (orange); beyond -> No Return (red). "
             "Default 120 (~4 months).")

    # --- Overdue campaign target (nature 'tempo' of the Ruptura report) ------
    campaign_stale_days = fields.Integer(
        string='Campaign overdue after (days)', default=30,
        config_parameter='soc_settlement.campaign_stale_days',
        help="A running campaign's customer who has not been settled (acerto) "
             "within this many days is flagged Overdue in the Ruptura report: "
             "the target is not being pursued and nobody noticed. The nightly "
             "cron checks this. Default 30 days.")
