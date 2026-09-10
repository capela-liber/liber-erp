/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * The person who posted an invoice to a sister company sees the mirror
 * (07/09/2026). Two tours, because the two documents live in two companies
 * and the web client shows one company at a time:
 *
 *   mirror_link_source_tour  - on the source invoice: the Mirror button is
 *                              there, with the count.
 *   mirror_link_mirror_tour  - on the mirror: the Source button, and the
 *                              "Source document" field in Other Info.
 *
 * Run live from the browser console (developer mode):
 *     odoo.startTour("mirror_link_source_tour")
 * or headless from tests/test_tour_mirror_link.py, which sets the URL of the
 * record under test.
 */
registry.category("web_tour.tours").add("mirror_link_source_tour", {
    steps: () => [
        {
            trigger: "button[name='action_open_mirror'] .o_stat_value:contains('1')",
            content: "The source shows one mirror in the sister company",
        },
        {
            trigger: "button[name='action_open_mirror']",
            content: "The Mirror smart button is clickable",
        },
    ],
});

registry.category("web_tour.tours").add("mirror_link_mirror_tour", {
    steps: () => [
        {
            trigger: "button[name='action_open_mirror_source']",
            content: "The mirror shows the Source smart button",
        },
        {
            trigger: "a.nav-link:contains('Other Info'), a.nav-link:contains('Outras informações')",
            content: "Open the Other Info tab",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='auto_invoice_id']",
            content: "The Source document field names the origin",
        },
    ],
});
