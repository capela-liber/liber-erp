/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Regression tours for the contract smart buttons: the whole point of the
 * buttons is NAVIGATION, so only a real browser click proves them. Each tour
 * starts on a contract form prepared by the Python test (one royalty line,
 * one analytic account) and asserts the click actually LANDS somewhere:
 *
 *   - "Contas Analíticas" with a single account must open that account's
 *     FORM (not a list of one);
 *   - "Favorecidos" with a single beneficiary must open the partner's card.
 *
 * Run live from the browser console (developer mode) on a contract form:
 *     odoo.startTour("contract_analytics_link_tour")
 */
registry.category("web_tour.tours").add("contract_analytics_link_tour", {
    steps: () => [
        {
            trigger: "button[name='action_view_contract_analytics']",
            content: "Open the contract's analytic account",
            run: "click",
        },
        {
            // The analytic account form has the plan field; a silent
            // non-navigation (the reported bug) never renders it.
            trigger: ".o_form_view .o_field_widget[name='plan_id']",
            content: "Landed on the analytic account form",
        },
    ],
});

registry.category("web_tour.tours").add("contract_beneficiaries_link_tour", {
    steps: () => [
        {
            trigger: "button[name='action_view_contract_beneficiaries']",
            content: "Open the contract's beneficiary",
            run: "click",
        },
        {
            trigger: ".o_breadcrumb .active:contains('Machado de Assis')",
            content: "Landed on the beneficiary's partner card",
        },
    ],
});

// Zerar analítico, como gerente: o botão aparece, a confirmação abre, e o
// clique termina numa notificação (e não num Access Error).
registry.category("web_tour.tours").add("contract_reset_analytics_tour", {
    steps: () => [
        {
            trigger: "button[name='action_reset_analytics']",
            content: "Reset the contract's analytic entries",
            run: "click",
        },
        {
            trigger: ".modal-footer button.btn-primary",
            content: "Confirm the reset",
            run: "click",
        },
        {
            trigger: ".o_notification:contains('1')",
            content: "The notification says how many entries were erased",
        },
    ],
});
