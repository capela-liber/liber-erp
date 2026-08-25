/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Screen tour for the MONTHLY MAP, fired by hand from the contract.
 *
 * The button walks the same path the monthly cron walks: it opens the month's
 * operation (CO) for this customer — or reuses the one already being worked
 * on — reads the shelf into it, and e-mails the customer that CO's map. The
 * ORM tests prove the rule (who gets it, when, once a month); they prove
 * nothing about the screen, and the screen is where this lives for the
 * commercial team: a contract, a button, an e-mail that leaves.
 *
 * And there is a specific thing only a tour can catch here. Sending the map is
 * not a write on the contract: it renders a QWeb report, creates an
 * `ir.attachment`, and queues a `mail.mail`. A profile that reads and writes
 * `consignment.agreement` perfectly may still hit an Access Error on any of the
 * three -- exactly the ACL hole the house rule of 22/08/2026 was written for
 * (the Editorial purchase form that passed the ORM and died on `stock.picking`).
 * So this tour logs in as a plain Consignment USER, never as admin: admin
 * passes everything and proves nothing about the profile.
 *
 * The world (customer with an e-mail, active agreement, books on the shelf) is
 * seeded by tests/test_tour_mapa_avulso.py -- putting stock on a shelf is
 * warehouse work, and a tour is for the decision. To run it live, seed a shelf
 * first, then:
 *
 *     odoo.startTour("soc_mapa_avulso_tour")
 *
 * The button is matched by `name=`, never by its label: the base runs in pt_BR
 * and the label reads "Enviar mapa" there.
 *
 * Starts straight at the action: the apps-menu drawer is flaky under
 * web_responsive (see soc_acerto_tour).
 */

registry.category("web_tour.tours").add("soc_mapa_avulso_tour", {
    url: "/odoo/action-liber_soc_agreements.action_consignment_agreement",
    steps: () => [
        {
            // Na CÉLULA, não na linha: o handler que abre o formulário está na
            // célula, e um clique na linha crua não navega (visto na captura
            // de /tmp/odoo_tests/.../screenshots, que mostrava a lista ainda
            // aberta no passo seguinte).
            trigger: ".o_data_row:contains('Livraria do Mapa') .o_data_cell[name='partner_id']",
            content: "Open the customer's consignment agreement",
            run: "click",
        },
        {
            // The shelf the map is about. Also proves the profile can READ the
            // stat button, which reads stock.quant through the agreement.
            trigger: "button[name='action_view_shelf'] .o_stat_value:contains('12')",
            content: "The shelf holds the 12 copies the map will report",
        },
        {
            trigger: "button[name='action_send_consignment_map']",
            content: "Send the map now, with no settlement open",
            run: "click",
        },
        {
            // The notification is the operator's receipt. Success (not warning)
            // means it was actually queued: the action returns a warning toast
            // when nothing went out. The colour lives on the little bar at the
            // side of the toast (`o_notification_bar bg-{type}`), not on the
            // toast itself -- checked in web/static/src/core/notifications
            // after the first run failed here.
            trigger: ".o_notification .o_notification_bar.bg-success",
            content: "The map was queued for this customer",
            // 30s: este clique não é um write, é um PDF. O servidor renderiza
            // o QWeb, chama o wkhtmltopdf e grava o anexo antes de responder,
            // e com a suíte inteira rodando junto isso passa dos 10s padrão --
            // o passo falhava sozinho na suíte cheia e passava rodando só ele.
            timeout: 30000,
        },
        {
            // O contador subiu de 0 para 1: prova que a operação nasceu E que o
            // formulário se recarregou. Sem o `next: soft_reload` do toast este
            // passo falha -- que é exatamente o defeito que ele guarda.
            trigger: "button[name='action_view_settlements'] .o_stat_value:contains('1')",
            content: "The month's operation is now on the contract",
        },
    ],
});
