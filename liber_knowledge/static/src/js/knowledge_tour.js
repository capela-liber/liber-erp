/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * An internal user reads the Liber manuals in the Manuals reader (25/09/2026).
 *
 * The profile is the plainest there is: an internal user with no extra group.
 * The tour walks what a reader does: land on the map, open an area, open a
 * manual, follow a link to another manual without leaving the reader, and
 * search. The editing buttons must not show for this profile.
 *
 * Run it live from the browser console (developer mode):
 *     odoo.startTour("liber_knowledge_tour")
 * or headless from tests/test_tour_knowledge.py.
 */
registry.category("web_tour.tours").add("liber_knowledge_tour", {
    url: "/odoo/manuais",
    steps: () => [
        {
            trigger: ".o_liber_reader .o_liber_card:contains('Consignação')",
            content: "The reader lands on the map of areas",
            run: "click",
        },
        {
            trigger: ".o_liber_reader .o_liber_card:contains('Acerto de consignação')",
            content: "The area lists its manuals",
            run: "click",
        },
        {
            trigger: ".o_liber_content h2",
            content: "The manual renders in the reading pane",
        },
        {
            trigger: ".o_liber_content img[src^='/liber_site/static/docs/img/']",
            content: "The screenshots come along",
        },
        {
            trigger: ".o_liber_tree .o_liber_active:contains('Acerto de consignação')",
            content: "The tree marks the open manual",
        },
        {
            trigger: ".o_liber_reader:not(:has(.o_liber_edit)):not(:has(.o_liber_new))",
            content: "A reader gets no editing buttons",
        },
        {
            trigger: ".o_liber_content a[href^='/odoo/manuais/']",
            content: "Follow a link to another manual",
            run: "click",
        },
        {
            trigger: ".o_liber_title:not(:contains('Acerto de consignação'))",
            content: "The other manual opens inside the reader",
        },
        {
            trigger: ".o_liber_search_input",
            content: "Search the manuals",
            run: "edit prateleira",
        },
        {
            trigger: ".o_liber_hit a:contains('Acordos de consignação')",
            content: "The search finds manuals by their text",
            run: "click",
        },
        {
            trigger: ".o_liber_title:contains('Acordos de consignação')",
            content: "The hit opens the manual",
        },
    ],
});
