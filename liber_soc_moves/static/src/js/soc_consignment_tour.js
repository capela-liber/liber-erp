/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Screen tour for the consignment relationship (SOC).
 *
 * Drives the agreement lifecycle through the real UI — the screen flow the
 * module actually offers (physical shipments are engine-made, not typed in):
 *   create an agreement for a partner -> save -> Activate (the shelf location
 *   is born: the "On shelf" stat button appears) -> Close -> Closed.
 *
 * The partner ("Livraria do Tour") is seeded by tests/test_tour.py with no
 * agreement yet. To run it live, create such a partner first (is_company,
 * without an open agreement), then:
 *
 *     odoo.startTour("soc_consignment_tour")
 *
 * Starts straight at the agreements action: navigating through the apps-menu
 * drawer is flaky under web_responsive (see copyright_contracts_tour).
 */
registry.category("web_tour.tours").add("soc_consignment_tour", {
    url: "/odoo/action-liber_soc_agreements.action_consignment_agreement",
    steps: () => [
        {
            trigger: ".o_list_button_add",
            content: "Create a consignment agreement",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='partner_id'] input",
            content: "Pick the bookshop",
            run: "edit Livraria do Tour",
        },
        {
            // :not(.o_m2o_dropdown_option) -- an EXISTING bookshop, never the
            // 'Create "Livraria do Tour"' quick-add, whose label contains the
            // name too. Otherwise a run against an unseeded base quietly creates
            // its own partner and the tour passes without proving anything.
            trigger: ".o-autocomplete--dropdown-item:not(.o_m2o_dropdown_option):contains('Livraria do Tour')",
            run: "click",
        },
        {
            trigger: ".o_form_button_save",
            content: "Save the agreement (still Draft)",
            run: "click",
        },
        {
            trigger: "button[name='action_activate']",
            content: "Activate: this is what creates the shelf location",
            run: "click",
        },
        {
            // match by the raw selection value (data-value), not the label:
            // the status label is translated (pt_BR: "Ativo"), so :contains('Active')
            // would break on any non-English database.
            trigger: ".o_statusbar_status button.o_arrow_button_current[data-value='active']",
            content: "The agreement is Active",
        },
        {
            // the stat button is invisible until location_id is set, so its
            // presence proves the shelf was created by the activation
            trigger: "button[name='action_view_shelf']",
            content: "The 'On shelf' button proves the shelf exists",
        },
        {
            trigger: "button[name='action_close']",
            content: "Close the agreement (allowed: the shelf is empty)",
            run: "click",
        },
        {
            // data-value again (pt_BR label is "Encerrado") — language-independent
            trigger: ".o_statusbar_status button.o_arrow_button_current[data-value='closed']",
            content: "Lifecycle complete: Draft -> Active -> Closed",
        },
    ],
});
