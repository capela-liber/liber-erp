/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * A devolução (CR), no perfil que a opera: o Comercial.
 *
 * O test_logistica.py já prova no ORM que o comercial solta o movimento; este
 * tour prova a TELA, e nasceu de um acidente de produção (21/08/2026): o
 * clique "Liberar para Logística" da CR/2026/00027 morreu na constraint
 * name_uniq do stock.picking ("A referência deve ser exclusiva para cada
 * empresa"). O ORM mede o que o teste pediu; o tour mede o que a tela pede —
 * e este caminho passa exatamente pelo clique que quebrou.
 *
 * O mundo (livraria com prateleira ativa, livro consignado nela, a CR em
 * rascunho) é semeado por tests/test_tour_comercial.py — a CR real nasce do
 * acerto (a ação de Devoluções tem create: False), então o tour começa na
 * lista e ABRE a que existe. Para rodar ao vivo, tenha uma CR em rascunho de
 * uma "Livraria da Devolucao" e:
 *
 *     odoo.startTour("comercial_devolucao_tour")
 *
 * Direto na ação: o menu de apps é instável sob web_responsive (ver
 * copyright_contracts_tour).
 */
registry.category("web_tour.tours").add("comercial_devolucao_tour", {
    url: "/odoo/action-liber_soc_moves.action_consignment_move",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "A lista de Devoluções abre para o perfil comercial",
        },
        {
            trigger: ".o_data_row:contains('Livraria da Devolucao') td.o_data_cell:not(.o_list_record_selector)",
            content: "Abre a devolução em rascunho",
            run: "click",
        },
        {
            // o contêiner do controlador, não .o_form_view — ver editorial_compras_tour
            trigger: ".o_form_view_container",
            content: "A CR abre no formulário",
        },
        {
            trigger: "button[name='action_confirm']",
            content: "Confirmar: trava o pedido de devolução (ainda sem logística)",
            run: "click",
        },
        {
            // pelo data-value, nunca pelo rótulo: em pt_BR o estado vira
            // "Aguardando" e um :contains('Waiting') quebraria sem regressão
            trigger: ".o_statusbar_status button.o_arrow_button_current[data-value='waiting']",
            content: "A CR está aguardando os livros voltarem",
        },
        {
            // O CLIQUE DO ACIDENTE: cria o stock.picking na série COM/IN.
            trigger: "button[name='action_release']",
            content: "Liberar para Logística: nasce a transferência de retorno",
            run: "click",
        },
        {
            trigger: ".o_statusbar_status button.o_arrow_button_current[data-value='confirmed']",
            content: "A CR confirmou — o clique que quebrava em produção passou",
        },
        {
            // o stat button é invisível até picking_id existir: a presença
            // dele É a prova de que a transferência nasceu
            trigger: "button[name='action_view_picking']",
            content: "O botão Transfer prova que o picking existe",
        },
    ],
});
