/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * End-to-end regression tour for Copyright Contracts.
 *
 * Drives the whole life of a contract through the real UI:
 *   create a contract -> the renewal term auto-fills from the dates -> add a
 *   royalty line (beneficiary x work) with two copies tiers and a recoupable
 *   advance -> save -> validate -> renew -> reassign the responsible via the
 *   ⚙ Action menu -> cancel.
 *
 * Run it live from the browser console (developer mode, on the `testing` db):
 *     odoo.startTour("copyright_contracts_tour")
 * or headless from the Python HttpCase test (see tests/test_tour.py).
 *
 * Notes for maintainers:
 * - Date fields need "&& press Enter" to COMMIT the value; without it the change
 *   event never fires and the renewal-term onchange never runs.
 * - The beneficiary/work are demo records shipped with base/product demo data.
 *   If you run this on a DB without demo data, swap the names below or
 *   quick-create the records.
 */
registry.category("web_tour.tours").add("copyright_contracts_tour", {
    // Straight to the contracts action: navigating through the apps menu is
    // flaky under web_responsive (the drawer animates and the click can land
    // mid-transition, leaving the tour stranded on the default app).
    url: "/odoo/action-liber_copyright_contracts.action_edlab_contract",
    steps: () => [
        // --- create a contract -------------------------------------------------
        {
            trigger: ".o_list_button_add",
            content: "Create a new contract",
            run: "click",
        },
        // --- dates and the auto-filled renewal term ---------------------------
        {
            trigger: ".o_field_widget[name='signature_date'] input",
            content: "Set the signature date (press Enter to commit the value)",
            run: "edit 01/01/2026 && press Enter",
        },
        {
            trigger: ".o_field_widget[name='expiration_date'] input",
            content: "Set the expiration date (renewal term should auto-fill)",
            run: "edit 01/01/2031 && press Enter",
        },
        {
            trigger: ".o_field_widget[name='renewal_period_years'] input:value(5)",
            content: "Renewal term was suggested from the dates",
        },
        // --- royalty line: beneficiary x work, two tiers, an advance ----------
        {
            trigger: ".o_notebook .nav-link:contains('Royalties')",
            content: "Open the Royalties tab",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='royalty_line_ids'] .o_field_x2many_list_row_add a",
            content: "Add a royalty line",
            run: "click",
        },
        {
            trigger: ".modal .o_field_widget[name='partner_id'] input",
            content: "Pick the beneficiary",
            run: "edit Willie",
        },
        {
            trigger: ".o-autocomplete--dropdown-item:contains('Willie Burke')",
            content: "Select Willie Burke",
            run: "click",
        },
        {
            trigger: ".modal .o_field_widget[name='product_id'] input",
            content: "Pick the work",
            run: "edit Customizable Desk",
        },
        {
            trigger: ".o-autocomplete--dropdown-item:contains('Customizable Desk')",
            content: "Select the work",
            run: "click",
        },
        {
            trigger: ".modal .o_field_widget[name='recoupable_advance'] input",
            content: "Set a recoupable advance",
            run: "edit 500",
        },
        // first tier: 0 -> 1000 copies at 10%
        {
            trigger: ".modal .o_field_widget[name='tier_ids'] .o_field_x2many_list_row_add a",
            content: "Add the first copies tier",
            run: "click",
        },
        {
            trigger: ".modal .o_selected_row .o_field_widget[name='qty_from'] input",
            run: "edit 0",
        },
        {
            trigger: ".modal .o_selected_row .o_field_widget[name='qty_to'] input",
            run: "edit 1000",
        },
        {
            trigger: ".modal .o_selected_row .o_field_widget[name='percentage'] input",
            run: "edit 10",
        },
        // second tier: 1001 -> no limit at 12%
        {
            trigger: ".modal .o_field_widget[name='tier_ids'] .o_field_x2many_list_row_add a",
            content: "Add the second copies tier (commits the first row)",
            run: "click",
        },
        {
            trigger: ".modal .o_selected_row .o_field_widget[name='qty_from'] input",
            run: "edit 1001",
        },
        {
            trigger: ".modal .o_selected_row .o_field_widget[name='percentage'] input",
            run: "edit 12",
        },
        {
            trigger: ".modal-footer .o_form_button_save",
            content: "Save & close the royalty line",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='royalty_line_ids'] td:contains('Willie Burke')",
            content: "The royalty line is on the contract",
        },
        // --- save, then walk the status bar -----------------------------------
        {
            trigger: ".o_form_button_save",
            content: "Save the contract",
            run: "click",
        },
        {
            trigger: "button[name='action_validate']",
            content: "Validate the contract",
            run: "click",
        },
        {
            trigger: ".o_statusbar_status button.o_arrow_button_current:contains('Valid')",
            content: "The contract is now Valid",
        },
        {
            trigger: "button[name='action_renew']",
            content: "Renew the contract",
            run: "click",
        },
        {
            trigger: ".o_statusbar_status button.o_arrow_button_current:contains('Renewed')",
            content: "The contract is now Renewed",
        },
        // --- reassign the responsible through the ⚙ Action menu ---------------
        {
            trigger: ".o_cp_action_menus .dropdown-toggle",
            content: "Open the Action menu",
            run: "click",
        },
        {
            trigger: ".o-dropdown--menu .dropdown-item:contains('Reassign')",
            content: "Reassign Responsible",
            run: "click",
        },
        {
            trigger: ".modal .o_field_widget[name='user_id'] input",
            content: "Pick the new responsible",
            run: "edit Marc Demo",
        },
        {
            trigger: ".o-autocomplete--dropdown-item:contains('Marc Demo')",
            run: "click",
        },
        {
            trigger: ".modal button[name='action_apply']",
            content: "Apply the reassignment",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='user_id'] input:value(Marc Demo)",
            content: "The responsible is now Marc Demo",
        },
        // --- cancel -----------------------------------------------------------
        {
            trigger: "button[name='action_cancel']",
            content: "Cancel the contract",
            run: "click",
        },
        {
            trigger: ".o_statusbar_status button.o_arrow_button_current:contains('Cancelled')",
            content: "The contract is now Cancelled",
        },
    ],
});
