/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * The royalties manager walks the legacy path on the real screen: the
 * contract opens, the "Legacy Sales" tab shows the option and the totals,
 * the smart button lands on the legacy rows of the contracted work, and a
 * row opens with its CFOP and effect. The ORM tests prove the numbers;
 * this proves the screen asks for nothing the profile cannot read.
 *
 * Run it live from the browser console (developer mode):
 *     odoo.startTour("legacy_sales_tour")
 */
registry.category("web_tour.tours").add("legacy_sales_tour", {
    steps: () => [
        {
            trigger: ".o_form_view_container",
            content: "The contract opens for the manager",
        },
        {
            trigger: ".o_notebook .nav-link:contains('Legacy Sales')",
            content: "Open the Legacy Sales tab",
            run: "click",
        },
        {
            trigger: ".o_notebook [name='legacy_enabled']",
            content: "The option is on the tab",
        },
        {
            trigger: ".o_notebook [name='legacy_qty']",
            content: "The totals read",
        },
        {
            // With more layers on the contract (support, documents) the
            // box folds its last buttons into "More" at the tour's width;
            // unfold it when it is there, do nothing when it is not.
            trigger: ".o-form-buttonbox",
            content: "Unfold the button box if it is folded",
            run: () => {
                const more = document.querySelector(".o-form-buttonbox .o_button_more");
                if (more) {
                    more.click();
                }
            },
        },
        {
            trigger: "button[name='action_view_legacy_sales']",
            content: "Jump to the legacy rows of the contracted works",
            run: "click",
        },
        {
            trigger: ".o_list_view",
            content: "The legacy sales list opens",
        },
        {
            trigger: ".o_searchview_facet .o_facet_value:contains('Counts for royalties')",
            content: "Only the rows that count are shown",
        },
        {
            // A row WITH a CFOP: the list opens on the newest month, whose
            // rows in the fixture have none, and an empty read-only field
            // leaves nothing for the next step to find.
            trigger: ".o_data_row:contains('5113') td.o_data_cell:not(.o_list_record_selector)",
            content: "Open a consignment settlement",
            run: "click",
        },
        {
            trigger: ".o_form_view_container [name='cfop']:contains('5113')",
            content: "The CFOP of the line reads",
        },
        {
            trigger: ".o_form_view_container [name='effect']",
            content: "And so does its effect on royalties",
        },
    ],
});
