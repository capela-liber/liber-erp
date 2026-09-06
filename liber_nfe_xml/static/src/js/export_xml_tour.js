/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * The accountant's export, driven through the real screen (04/09/2026).
 *
 * The ORM tests pin down the SHAPE of the package (which XML lands in which
 * folder, what the relacao.csv lists). What they cannot see is the door: that
 * the wizard opens for a plain user, that the month list renders with its
 * checkboxes, and that ticking one and pressing Export comes back with a file
 * to download instead of an access error. That is what this walks.
 *
 * Run it live from the browser console (developer mode):
 *     odoo.startTour("nfe_xml_export_tour")
 * or headless from tests/test_tour_export_xml.py.
 */
registry.category("web_tour.tours").add("nfe_xml_export_tour", {
    // Straight to the action: the apps drawer is flaky under web_responsive,
    // and what is under test is the export, not the menu animation.
    url: "/odoo/action-liber_nfe_xml.xml_export_wizard",
    steps: () => [
        {
            trigger: ".o_dialog .o_form_view",
            content: "The export wizard opens for this profile",
        },
        {
            trigger: ".o_dialog [name='month_ids'] .o_data_row",
            content: "The months are listed, one row each",
        },
        {
            // The checkbox is a boolean_toggle: clicking the cell would only
            // select the row, not tick it.
            trigger: ".o_dialog [name='month_ids'] .o_data_row:first [name='selected'] input",
            content: "Tick the month to send",
            run: "click",
        },
        {
            trigger: ".o_dialog button[name='action_export']",
            content: "Build the package",
            run: "click",
        },
        {
            // The wizard reopens on itself in the 'done' state: the summary and
            // the file to download are the proof it got through.
            trigger: ".o_dialog [name='summary']",
            content: "The wizard says what went into the package",
        },
        {
            trigger: ".o_dialog [name='file']",
            content: "And hands over the ZIP to download",
        },
    ],
});
