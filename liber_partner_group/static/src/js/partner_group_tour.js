/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * The commercial manager runs the economic groups (23/08/2026).
 *
 * The ORM tests prove the compute and the ACL; these tours prove the way
 * there: the configuration list opens for the profile, the group form shows
 * its members, and the partner form renders the two new fields. It is the
 * class of failure only the screen catches -- ACL missing on a model the
 * view reads, inherit anchored on the wrong node, field that does not
 * render (the Editorial purchases lesson).
 *
 * Straight to the action, as the house tours do: the menu walk is flaky
 * under web_responsive and is not what is under test.
 *
 * Run live from the browser console (developer mode):
 *     odoo.startTour("partner_group_config_tour")
 */
registry.category("web_tour.tours").add("partner_group_config_tour", {
    url: "/odoo/action-liber_partner_group.action_partner_group",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "The economic groups open for the commercial manager",
        },
        {
            // The list is editable: clicking a cell edits it in place. The
            // way INTO the form is the open-form button the list view adds
            // per row (`open_form_view`) -- the failed screenshot told this.
            trigger: ".o_data_row:contains('Travessa do Tour') " +
                     ".o_list_record_open_form_view",
            content: "Open the group",
            run: "click",
        },
        {
            // The o2m list of members must render -- it reads res.partner
            // (and its legal_name) through this profile's rights.
            trigger: ".o_form_view_container .o_field_x2many_list " +
                     ".o_data_row:contains('Travessa do Tour Botafogo')",
            content: "The member store is listed inside the group",
        },
    ],
});

registry.category("web_tour.tours").add("partner_group_ficha_tour", {
    // The test opens the store's form directly (the record id is not known
    // at registry time, so the test passes the URL to start_tour).
    steps: () => [
        {
            trigger: ".o_form_view_container",
            content: "The store's card opens",
        },
        {
            trigger: ".o_field_widget[name='legal_name']",
            content: "The legal name renders under the document",
        },
        {
            trigger: ".o_field_widget[name='partner_group_id'] " +
                     "input:value('Travessa do Tour')",
            content: "The economic group is on the card, filled",
        },
    ],
});
