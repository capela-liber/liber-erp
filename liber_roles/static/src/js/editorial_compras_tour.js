/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Editorial reads the purchase orders (22/08/2026).
 *
 * The ACL is what really guards this (read-only on purchase.order and its
 * line); the menu is only the door. This tour drives the door: it logs in as
 * the editorial assistant, opens Purchase Orders, narrows to the ones that
 * carry books through the "Com livros" filter, and opens one.
 *
 * Run it live from the browser console (developer mode, on `testing`):
 *     odoo.startTour("editorial_compras_tour")
 * or headless from tests/test_tour_editorial.py.
 */
registry.category("web_tour.tours").add("editorial_compras_tour", {
    // Straight to the action: walking the apps drawer is flaky under
    // web_responsive, and what is under test here is the reading, not the menu
    // animation. That the menu EXISTS for this profile is what the ACL test
    // and the door itself already assert.
    url: "/odoo/action-purchase.purchase_form_action",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "The purchase orders open for the editorial profile",
        },
        {
            trigger: ".o_searchview_dropdown_toggler",
            content: "Open the filters",
            run: "click",
        },
        {
            // O item do menu de filtros é um CheckboxItem com `o_menu_item`,
            // não um `dropdown-item`: o nome mudou e o tour foi quem contou.
            trigger: ".o_filter_menu .o_menu_item:contains('Com livros')",
            content: "Narrow to the orders that carry books",
            run: "click",
        },
        {
            trigger: ".o_searchview_facet .o_facet_value:contains('Com livros')",
            content: "The filter is on",
        },
        {
            trigger: ".o_data_row:first td.o_data_cell:not(.o_list_record_selector)",
            content: "Open the print run",
            run: "click",
        },
        {
            // `o_form_view_container` e não `o_form_view`: é o contêiner que o
            // controlador do formulário monta, e é o que existe no DOM.
            trigger: ".o_form_view_container",
            content: "The order opens: reading is what this profile came for",
        },
        {
            // Sem `.o_field_widget`: num formulário só de leitura o campo não
            // recebe o wrapper de edição, e o seletor mais estreito não acha
            // nada. Foi o passo 6 quem contou.
            trigger: ".o_form_view_container [name='partner_id']",
            content: "The supplier reads",
        },
    ],
});
