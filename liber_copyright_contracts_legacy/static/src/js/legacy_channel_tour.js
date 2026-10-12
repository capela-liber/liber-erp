/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * The royalties manager marks the channel of a legacy sale by hand: the
 * row opens, the channel is picked among the sales teams, and once saved
 * the row reads as a special sale (special channel + 20% discount, above
 * the 15% minimum of the test). Proves the profile reads the sales teams
 * and can write the one field it is meant to write.
 *
 * Run it live from the browser console (developer mode):
 *     odoo.startTour("legacy_channel_tour")
 */
registry.category("web_tour.tours").add("legacy_channel_tour", {
    steps: () => [
        {
            trigger: ".o_form_view_container [name='cfop']:contains('5113')",
            content: "The legacy sale opens for the manager",
        },
        {
            trigger: ".o_form_view_container [name='team_id'] input",
            content: "Type the special channel",
            run: "edit Vendas especiais",
        },
        {
            trigger: ".o-autocomplete--dropdown-item:contains('Vendas especiais (tour)')",
            content: "Pick it",
            run: "click",
        },
        {
            trigger: ".o_form_button_save",
            content: "Save",
            run: "click",
        },
        {
            trigger: ".o_form_view_container [name='special_sale'] input:checked",
            content: "The row is now a special sale",
        },
    ],
});
