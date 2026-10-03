/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * A reader talks about a file (30/09/2026).
 *
 * The folder grants this profile read and nothing more; the chatter must
 * still open and take a comment -- talking about a file is not editing it.
 * Run it live from the browser console (developer mode, on `testing`):
 *     odoo.startTour("cloud_file_chatter_tour")
 * or headless from tests/test_tour_chatter.py.
 */
registry.category("web_tour.tours").add("cloud_file_chatter_tour", {
    url: "/odoo/action-liber_github.action_liber_github_file",
    steps: () => [
        {
            trigger: ".o_list_view .o_data_row td.o_data_cell:contains('TOUR_CAPA.pdf')",
            content: "Open the file the reader can see",
            run: "click",
        },
        {
            trigger: ".o_form_view .o-mail-Chatter",
            content: "The chatter is on the file's form",
        },
        {
            trigger: ".o-mail-Chatter-topbar button:contains('Log note')",
            content: "Open a note",
            run: "click",
        },
        {
            trigger: ".o-mail-Composer-input",
            content: "Write it",
            run: "edit Capa conferida pelo leitor",
        },
        {
            trigger: ".o-mail-Composer-send:enabled",
            content: "Post it",
            run: "click",
        },
        {
            trigger: ".o-mail-Message-body:contains('Capa conferida pelo leitor')",
            content: "The note is on the file",
        },
        {
            trigger: ".o-mail-Chatter-topbar button:contains('Activity')",
            content: "Activities are offered too",
        },
    ],
});
