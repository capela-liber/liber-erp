/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * The contract's documents, as the contracts manager sees them: the tab
 * lists the linked files with the main one first, and the header offers to
 * open it. Opening itself leaves Odoo (provider link), so the tour stops at
 * the door; the gate is proven in test_contract_documents.py.
 */
registry.category("web_tour.tours").add("contract_documents_tour", {
    steps: () => [
        {
            trigger: ".o_form_view_container button[name='action_open_main_document']",
            content: "The header offers to open the contract document",
        },
        {
            trigger: ".o_notebook .nav-link:contains('Documents')",
            content: "Open the Documents tab",
            run: "click",
        },
        {
            trigger: ".o_notebook .o_data_row:first .o_data_cell[name='name']:contains('SERMOES_CONTRATO')",
            content: "The main document comes first",
        },
        {
            trigger: ".o_notebook .o_data_row .o_data_cell[name='note']:contains('Aditivo')",
            content: "The amendment is listed too",
        },
        {
            trigger: ".o_form_view_container [name='location']:contains('SERMOES_CONTRATO')",
            content: "The Location follows the main document",
        },
    ],
});
