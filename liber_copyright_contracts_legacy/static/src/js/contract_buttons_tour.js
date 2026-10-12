/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Every smart button of the contract, clicked from the contract form, lands
 * where it says (09/10/2026: reported as "not leading anywhere" on a
 * contract with legacy sales). One step per button, back to the contract in
 * between through the breadcrumb.
 */
const back = {
    trigger: ".o_breadcrumb .breadcrumb-item:not(.active):last a",
    content: "Back to the contract",
    run: "click",
};
const onContract = {
    trigger: ".o_form_view_container button[name='action_view_contract_beneficiaries']",
    content: "On the contract again",
};
// At the tour's 1366px the box folds its last buttons into "More".
const more = {
    trigger: ".o-form-buttonbox .o_button_more",
    content: "Unfold the rest of the button box",
    run: "click",
};

registry.category("web_tour.tours").add("contract_all_buttons_tour", {
    steps: () => [
        onContract,
        {
            trigger: "button[name='action_view_contract_beneficiaries']",
            content: "Beneficiaries",
            run: "click",
        },
        {
            trigger: ".o_breadcrumb .active:contains('Autor do Tour')",
            content: "Landed on the beneficiary",
        },
        back, onContract,
        {
            trigger: "button[name='action_view_contract_analytics'] .o_stat_text:contains('Analytic')",
            content: "Analytic accounts",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_field_widget[name='plan_id']",
            content: "Landed on the analytic account",
        },
        back, onContract,
        {
            trigger: "button[name='action_view_contract_analytics'] .o_stat_text:contains('Open')",
            content: "Open balance",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_field_widget[name='plan_id']",
            content: "Open balance lands on the analytic account",
        },
        back, onContract,
        {
            trigger: "button[name='action_view_contract_analytics'] .o_stat_text:contains('Paid')",
            content: "Paid",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_field_widget[name='plan_id']",
            content: "Paid lands on the analytic account",
        },
        back, onContract, more,
        {
            trigger: "button[name='action_view_legacy_sales']",
            content: "Legacy sales",
            run: "click",
        },
        {
            trigger: ".o_list_view .o_data_row",
            content: "Landed on the legacy sales",
        },
        back, onContract, more,
        {
            trigger: "button[name='action_view_bills_to_pay']",
            content: "Bills to pay",
            run: "click",
        },
        {
            trigger: ".o_list_view .o_data_row",
            content: "Landed on the bills to pay",
        },
        {
            trigger: ".o_breadcrumb:contains('2026/')",
            content: "The contract is still in the breadcrumb",
        },
    ],
});
