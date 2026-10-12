/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * A bipagem inteira, no perfil de quem opera o depósito: prateleira de
 * origem, dois bipes do mesmo livro, prateleira de destino. O leitor de mão
 * digita o código e um Enter; o tour faz o mesmo. O mundo (duas prateleiras
 * TST-, um livro com ISBN e 10 exemplares na primeira) é semeado por
 * tests/test_tour_bipagem.py, que confere os saldos no fim.
 *
 *     odoo.startTour("shelves_bipagem_tour")
 */
registry.category("web_tour.tours").add("shelves_bipagem_tour", {
    url: "/odoo/action-liber_stock_scan.action_scan",
    steps: () => [
        {
            trigger: ".o_liber_scan_input",
            content: "A tela de bipagem abre com o campo em foco",
            run: "edit TST-000001 && press Enter",
        },
        {
            trigger: ".o_liber_scan_origin:contains('TST-000001')",
            content: "A origem está aberta",
        },
        {
            trigger: ".o_liber_scan_input",
            content: "Primeiro exemplar",
            run: "edit 9780000000017 && press Enter",
        },
        {
            trigger: ".o_liber_scan_line .o_liber_scan_qty:contains('1')",
            content: "Uma linha com 1",
        },
        {
            trigger: ".o_liber_scan_input",
            content: "Segundo exemplar do mesmo livro",
            run: "edit 9780000000017 && press Enter",
        },
        {
            trigger: ".o_liber_scan_line .o_liber_scan_qty:contains('2')",
            content: "A mesma linha, agora com 2",
        },
        {
            // Um livro que NÃO está na prateleira de origem é recusado e a
            // tela continua onde estava.
            trigger: ".o_liber_scan_input",
            content: "Um livro de outra prateleira",
            run: "edit 9780000000024 && press Enter",
        },
        {
            trigger: ".o_liber_scan_message.alert-danger",
            content: "Recusado: não está na prateleira de origem",
        },
        {
            trigger: ".o_liber_scan_input",
            content: "A prateleira de destino fecha a transferência",
            run: "edit TST-000002 && press Enter",
        },
        {
            trigger: ".o_liber_scan_done:contains('INT')",
            content: "A transferência nasceu validada",
        },
        {
            trigger: "body:not(:has(.modal))",
            content: "E nenhuma caixa de erro subiu no caminho",
        },
    ],
});
