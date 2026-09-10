/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * O Plano de Contas com a barra lateral das RUBRICAS.
 *
 * O teste de ORM prova que `group_id` virou SQL e que o painel devolve a
 * árvore. Isto prova a TELA: que o `searchpanel` renderiza as rubricas pelo
 * nome, que elas ABREM em níveis (o filho só existe no DOM depois do clique
 * no pai), e que a folha filtra a lista. O ORM mede o que o teste pediu; o
 * tour mede o que a tela pede.
 *
 * O mundo é semeado por tests/test_tour_account_group_panel.py.
 */
registry.category("web_tour.tours").add("account_group_panel_tour", {
    url: "/odoo/action-account.action_account_form",
    steps: () => [
        {
            trigger: ".o_search_panel .o_search_panel_category_value",
            content: "O Plano de Contas abre com a barra lateral",
        },
        {
            // A prova central: a rubrica pelo nome. Antes daqui saía "1" e "1.".
            trigger: ".o_search_panel_label_title:contains('7 Ativo do Tour')",
            content: "A barra mostra a rubrica, não o recorte de dois caracteres",
            run: "click",
        },
        {
            // Hierarquia: este nó NÃO existia antes do clique acima.
            trigger: ".o_search_panel_label_title:contains('7.1 Ativo Circulante do Tour')",
            content: "O primeiro nível abriu: a árvore tem filhos",
            run: "click",
        },
        {
            trigger: ".o_search_panel_label_title:contains('7.1.1 Caixa e Equivalentes do Tour')",
            content: "O segundo nível abriu: três níveis, como o plano da casa",
            run: "click",
        },
        {
            trigger: ".o_list_view .o_data_row td:contains('Banco do Tour')",
            content: "A conta da rubrica está na lista",
        },
        {
            trigger: ".o_list_view",
            content: "E a lista ficou SÓ com as contas da rubrica",
            run: () => {
                const linhas = document.querySelectorAll(
                    ".o_list_view .o_data_row").length;
                if (linhas !== 2) {
                    throw new Error(
                        `Esperava 2 contas em "Caixa e Equivalentes", vi ${linhas}`);
                }
            },
        },
    ],
});
