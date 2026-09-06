/** @odoo-module **/

import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

// O caminho de quem monta um orçamento consolidado: abrir o app, entrar no
// orçamento, ver o campo "Also Consolidate" e a coluna Practical na linha.
// O teste ORM prova o número; só a tela prova que o campo existe para o
// PERFIL do orçamento — e não só para o admin, que passa em tudo.
registry.category("web_tour.tours").add("liber_budget_consolidado_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            content: "abrir o app de orçamentos",
            trigger: '.o_app[data-menu-xmlid="liber_budget.menu_budget_root"]',
            run: "click",
        },
        {
            content: "a lista de orçamentos chega",
            trigger: ".o_list_view",
        },
        // Clicar em ".o_data_row:first" abria coisa nenhuma: a captura de
        // falha mostrou a lista com dois registros e nenhum formulário. Numa
        // lista, o clique tem de cair numa CÉLULA, e mirar o registro pelo
        // NOME evita depender da ordenação -- que muda com os dados do banco.
        {
            content: "abrir o orçamento do teste",
            trigger: ".o_list_view .o_data_cell:contains('Tour Budget')",
            run: "click",
        },
        {
            content: "o formulário abriu",
            trigger: ".o_form_view",
        },
        // O campo da consolidação tem `groups="base.group_multi_company"`:
        // num banco de uma empresa só ele nem renderiza, e exigi-lo faria o
        // tour falhar por configuração, não por defeito.
        {
            content: "a coluna Practical está na linha do orçamento",
            trigger: ".o_form_view th:contains('Practical'), .o_form_view td[name='practical_amount']",
        },
    ],
});
