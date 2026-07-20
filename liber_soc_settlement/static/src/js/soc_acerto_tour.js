/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Screen tour for the ACERTO — the operation that makes the money.
 *
 * The lifecycle tour (soc_consignment_tour, in soc_moves) proves the paperwork:
 * an agreement is born, activated, closed. It proves nothing about the business,
 * and it passes precisely BECAUSE it never puts a book on a shelf (closing is
 * only allowed on an empty one).
 *
 * This is the other half, and it is the whole point of the module: a shelf with
 * two titles on it, and the operator doing the one thing an acerto is -- reading
 * the customer's report into the map and dispatching it. The two titles are the
 * two fates of a consigned book:
 *
 *   "Livro que Vende"  sold 4  -> a real sale (S) + the shelf baixa (ACERTO/)
 *                              -> and a replenishment Pedido (C) to refill it
 *   "Livro Parado"     sold 0  -> recalled: a return (CR), pure stock, no sale
 *
 * One Run, three correctly-typed documents. The stat buttons at the end are the
 * assertion the operator sees: each is invisible until its document exists (see
 * the form view), so their presence IS the fan-out. tests/test_tour.py then
 * checks the documents themselves -- a green button is not a sale.
 *
 * WHY TWO TITLES, and not one that both sells and returns: the acerto NETS a
 * return against a replenishment of the SAME title (see _onchange_quantities) --
 * sending 4 copies and recalling 2 of the same book would have the truck cross
 * itself, so it sends 2 and returns none. A tour that typed both on one line
 * would be testing a request the business refuses to honour, and would never see
 * a CR. Two titles is not a workaround; it is what an acerto looks like.
 *
 * The world (partner, active agreement, stock on both shelves) is seeded by
 * tests/test_tour.py: putting stock on a shelf is warehouse work, not a
 * decision, and the decision is what a tour is for. To run it live, seed a
 * shelf first, then:
 *
 *     odoo.startTour("soc_acerto_tour")
 *
 * Rows are matched by TITLE, never by position: the map is built from a dict of
 * quants, so row order is not a promise.
 *
 * Starts straight at the action: the apps-menu drawer is flaky under
 * web_responsive (see copyright_contracts_tour).
 */

const row = (title) => `.o_data_row:has([name='product_id']:contains('${title}'))`;

registry.category("web_tour.tours").add("soc_acerto_tour", {
    url: "/odoo/action-liber_soc_settlement.action_consignment_settlement",
    steps: () => [
        {
            trigger: ".o-kanban-button-new",
            content: "Open a new consignment operation",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='partner_id'] input",
            content: "Pick the bookshop we are settling with",
            run: "edit Livraria do Acerto",
        },
        {
            // :not(.o_m2o_dropdown_option) -- an EXISTING bookshop, never the
            // 'Create "Livraria do Acerto"' quick-add, whose label contains the
            // name too. Without this, a tour run against an unseeded base
            // silently invents a partner with no agreement and then dies further
            // down with "has no consignment agreement". Missing seed must fail
            // HERE, saying what is missing.
            trigger: ".o-autocomplete--dropdown-item:not(.o_m2o_dropdown_option):contains('Livraria do Acerto')",
            run: "click",
        },
        {
            // Loads the map from the shelf. It also saves the record: a header
            // button on a dirty form saves before running.
            trigger: "button[name='action_populate_from_shelf']",
            content: "Load the map: what we have on this customer's shelf",
            run: "click",
        },
        {
            // The lines only exist if the shelf was really read.
            trigger: `${row("Livro que Vende")} .o_data_cell[name='qty_on_shelf']:contains('10')`,
            content: "The map shows the 10 copies on the shelf",
        },
        {
            trigger: `${row("Livro que Vende")} .o_data_cell[name='qty_reported']`,
            content: "Type what the customer reported as sold",
            run: "click",
        },
        {
            trigger: `${row("Livro que Vende")} [name='qty_reported'] input`,
            run: "edit 4",
        },
        {
            // Moving to the other row COMMITS the first one, which fires the
            // onchange that suggests its replenishment.
            trigger: `${row("Livro Parado")} .o_data_cell[name='qty_return']`,
            content: "The other title did not sell: recall 2 copies",
            run: "click",
        },
        {
            // Row 1 is out of edit mode now, so this cell is text, not an input.
            trigger: `${row("Livro que Vende")} .o_data_cell[name='qty_replenish']:contains('4')`,
            content: "Place was suggested equal to what was sold — the shelf keeps its size",
        },
        {
            trigger: `${row("Livro Parado")} [name='qty_return'] input`,
            run: "edit 2",
        },
        {
            trigger: "button[name='action_run']",
            content: "Run: the single dispatcher of the operation",
            run: "click",
        },
        {
            trigger: ".o_statusbar_status button.o_arrow_button_current:contains('Confirmed')",
            content: "The operation is Confirmed",
        },
        {
            trigger: "button[name='action_view_sale_order']",
            content: "A real sale was born (S) — this IS a sale",
        },
        {
            trigger: "button[name='action_view_replenishment']",
            content: "A replenishment Pedido (C) — a movement, not a sale",
        },
        {
            trigger: "button[name='action_view_return']",
            content: "And a return (CR) — pure stock, never a sale",
        },
    ],
});
