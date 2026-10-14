/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * The Beneficiary tab on the contact, as the contracts manager sees it:
 * identification, the sensitive personal data block, regional, and the bank
 * list with the Pix columns. The ORM tests prove who may read what; this
 * proves the tab renders for the profile that fills it in.
 */
registry.category("web_tour.tours").add("beneficiary_tab_tour", {
    steps: () => [
        {
            trigger: ".o_form_view_container .o_notebook .nav-link:contains('Beneficiary')",
            content: "Open the Beneficiary tab",
            run: "click",
        },
        {
            trigger: ".o_notebook .o_field_widget[name='edlab_birthdate']",
            content: "Identification reads",
        },
        {
            trigger: ".o_notebook .o_field_widget[name='edlab_race']",
            content: "The personal data block is there for the manager",
        },
        {
            trigger: ".o_notebook .o_field_widget[name='lang']",
            content: "Regional reads",
        },
        {
            trigger: ".o_notebook [name='bank_ids'] .o_data_cell[name='edlab_pix_key']",
            content: "The Pix key shows in the bank list",
        },
        {
            trigger: ".o_notebook .nav-link:contains('Copyright Contracts')",
            content: "The contracts keep their own tab",
            run: "click",
        },
        {
            trigger: ".o_notebook .o_field_widget[name='edlab_royalty_line_ids']",
            content: "Royalty lines read there",
        },
    ],
});
