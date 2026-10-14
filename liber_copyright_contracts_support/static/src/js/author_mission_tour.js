/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * The royalties manager, who also works the support desk, walks a sent
 * mission on the real screen: the mission shows its tickets, a ticket
 * opens with the author and the contracts on it, and the author's card
 * lists it under Support tickets.
 */
registry.category("web_tour.tours").add("author_mission_tour", {
    steps: () => [
        {
            trigger: ".o_form_view_container .o_field_widget[name='ticket_count']",
            content: "The mission counts its tickets",
        },
        {
            trigger: ".o_notebook .nav-link:contains('Tickets')",
            content: "Open the Tickets tab",
            run: "click",
        },
        {
            trigger: ".o_notebook .o_data_row .o_data_cell[name='partner_id']:contains('Autor da Missão')",
            content: "One ticket per author",
        },
        {
            trigger: "button[name='action_view_tickets']",
            content: "Jump to the tickets",
            run: "click",
        },
        {
            trigger: ".o_kanban_view, .o_list_view",
            content: "The support view opens on this mission's tickets",
        },
        {
            trigger: ".o_kanban_record:contains('Autor da Missão'), .o_data_row:contains('Autor da Missão')",
            content: "Open the author's ticket",
            run: "click",
        },
        {
            trigger: ".o_form_view_container .o_field_widget[name='edlab_contract_ids']",
            content: "The contracts of the conversation are on the ticket",
        },
        {
            trigger: ".o_form_view_container .o_field_widget[name='edlab_mission_id']",
            content: "And so is the mission",
        },
    ],
});
