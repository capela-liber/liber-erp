/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * O inventário físico visto da tela, nos dois perfis que o operam.
 *
 * O assistente abre o Inventário físico, encontra a linha que o gerente lhe
 * pediu (o filtro "Minhas contagens" já vem ligado para quem não é
 * administrador), escreve o que contou e grava. A linha mostra a diferença e
 * NÃO oferece "Aplicar"; o cabeçalho não oferece "Aplicar tudo". O mundo (um
 * livro com 10 na prateleira, contagem pedida ao assistente) é semeado por
 * tests/test_tour_inventario.py, que confere o saldo no fim.
 *
 * Os passos miram a estrutura (nomes de campo e de botão), nunca o texto
 * traduzido; a sessão roda em inglês como os outros tours da casa.
 *
 *     odoo.startTour("count_assistente_tour")
 */
registry.category("web_tour.tours").add("count_assistente_tour", {
    // Direto na ação: o menu de apps é instável sob web_responsive.
    url: "/odoo/action-stock.action_view_inventory_tree",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "O Inventário físico abre para quem conta",
        },
        {
            trigger: ".o_data_row:contains('Livro da Contagem') td[name='inventory_quantity']",
            content: "A linha que o gerente pediu: clicar em Contado",
            run: "click",
        },
        {
            trigger: ".o_data_row.o_selected_row .o_field_widget[name='inventory_quantity'] input",
            content: "O que há na prateleira",
            run: "edit 7",
        },
        {
            trigger: ".o_list_button_save",
            content: "Gravar a contagem",
            run: "click",
        },
        {
            trigger: ".o_data_row:contains('Livro da Contagem') td[name='inventory_diff_quantity']:contains('3')",
            content: "A diferença aparece: havia 10, contou 7",
        },
        {
            trigger: ".o_data_row:contains('Livro da Contagem'):not(:has(button[name='action_apply_inventory']))",
            content: "E a linha não oferece Aplicar: isso é do gerente",
        },
        {
            trigger: "body:not(:has(button[name='action_apply_all']))",
            content: "Nem o cabeçalho oferece Aplicar tudo",
        },
    ],
});

/**
 * O gerente abre a mesma tela, vê o "Aplicar tudo" que o assistente não via,
 * procura o livro contado e aplica pela linha. A quantidade em mãos passa a
 * ser a contada.
 *
 *     odoo.startTour("count_gerente_tour")
 */
registry.category("web_tour.tours").add("count_gerente_tour", {
    url: "/odoo/action-stock.action_view_inventory_tree",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "O Inventário físico abre para o gerente",
        },
        {
            trigger: "button[name='action_apply_all']",
            content: "Para o gerente o Aplicar tudo está lá",
        },
        {
            trigger: ".o_searchview_input",
            content: "Procurar o livro contado",
            run: "edit Livro da Contagem",
        },
        {
            // A primeira sugestão é o produto: o primeiro campo da busca.
            trigger: ".o_searchview_autocomplete .o-dropdown-item.focus",
            content: "Aceitar a primeira sugestão (buscar por produto)",
            run: "click",
        },
        {
            trigger: ".o_data_row:contains('Livro da Contagem') button[name='action_apply_inventory']",
            content: "A linha contada oferece Aplicar ao gerente",
            run: "click",
        },
        {
            trigger: ".o_data_row:contains('Livro da Contagem'):not(:has(button[name='action_apply_inventory']))",
            content: "Aplicado: a contagem deixou de estar pendente",
        },
        {
            trigger: ".o_data_row:contains('Livro da Contagem') td[name='quantity']:contains('7')",
            content: "E a quantidade em mãos é a contada",
        },
        {
            trigger: "body:not(:has(.modal))",
            content: "Sem caixa de erro no caminho",
        },
    ],
});
