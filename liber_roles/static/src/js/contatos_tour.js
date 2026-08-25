/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Contacts, seen from a role (22/08/2026).
 *
 * The same three gestures every profile makes on the contact sheet: open the
 * app, open a contact, read the sheet. The tour carries no assertion about
 * WHICH profile may do it: it is driven once per role from the Python side,
 * and what it reports is where the screen breaks for whom.
 *
 * Deliberately short. What is under test is the door and the sheet, not the
 * whole Contacts app -- a long tour would just fail later for reasons that
 * have nothing to do with the role.
 */
registry.category("web_tour.tours").add("contatos_tour", {
    url: "/odoo/action-contacts.action_contacts",
    steps: () => [
        {
            trigger: ".o_kanban_view, .o_list_view",
            content: "The contacts open for this profile",
        },
        {
            trigger: ".o_kanban_record:not(.o_kanban_ghost):first, .o_data_row:first td.o_data_cell",
            content: "Open a contact",
            run: "click",
        },
        {
            trigger: ".o_form_view_container",
            content: "The sheet opens",
        },
        {
            trigger: ".o_form_view_container [name='email']",
            content: "The sheet renders: e-mail is on every contact form",
        },
    ],
});
