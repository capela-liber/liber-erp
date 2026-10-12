/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * The editorial assistant shortens a link (08/10/2026).
 *
 * "The editorial assistant and manager must be able to shorten a link at
 * edlab.press/r. Today only Paulo can." The ORM test proves the ACL; this
 * tour proves the screen: the Link Tracker list opens for the profile, New
 * exists, the form takes a target link and a title, and after saving the
 * short code (the `/r/<code>` part) is on the sheet.
 *
 * The title is typed on purpose: without one the core goes and fetches the
 * page title over HTTP, which a headless test has no business doing.
 *
 * Run it live from the browser console (developer mode, on `testing`):
 *     odoo.startTour("editorial_link_curto_tour")
 * or headless from tests/test_tour_editorial_link_curto.py.
 */
registry.category("web_tour.tours").add("editorial_link_curto_tour", {
    // Straight to the action, like the other editorial tour: what is under
    // test is the shortening, not the apps drawer. That the MENU exists for
    // this profile is what test_acessos asserts.
    url: "/odoo/action-link_tracker.link_tracker_action",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "The link tracker list opens for the editorial profile",
        },
        {
            trigger: ".o_list_button_add",
            content: "New: the button only renders when the ACL grants create",
            run: "click",
        },
        {
            trigger: ".o_form_view_container",
            content: "The link form opens",
        },
        {
            trigger: ".o_form_view .o_field_widget[name='url'] input",
            content: "Type the target link",
            run: "edit https://edlab.press/catalogo/livro-do-tour",
        },
        {
            trigger: ".o_form_view .o_field_widget[name='title'] input",
            content: "Type the title, so the core does not go fetch it",
            run: "edit Livro do Tour",
        },
        {
            trigger: ".o_form_button_save",
            content: "Save",
            run: "click",
        },
        {
            // `code` is `invisible="not code"` in the core form: it only
            // renders once the record is saved and the code was created.
            trigger: ".o_form_view .o_field_widget[name='code']",
            content: "The short code is on the sheet: the /r/ link exists",
        },
        {
            trigger: ".o_form_view .o_field_widget[name='short_url_host']",
            content: "And the host that goes before it",
        },
    ],
});
