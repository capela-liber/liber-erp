/** @odoo-module **/

import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

// O caminho de quem paga: abrir o relatório, ver o fornecedor, expandir o
// grupo e pular para o documento. O teste ORM prova a faixa; só a tela prova
// que o menu existe para o perfil, que a lista agrupa e que o botão renderiza.
registry.category("web_tour.tours").add("liber_aged_payable_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            content: "abrir o Financeiro",
            trigger: '.o_app[data-menu-xmlid="account.menu_finance"]',
            run: "click",
        },
        {
            content: "abrir o menu de relatórios",
            trigger: 'button[data-menu-xmlid="account.menu_finance_reports"]',
            run: "click",
        },
        {
            content: "entrar no Aged Payable",
            trigger:
                '.dropdown-item[data-menu-xmlid="liber_aged_payable.liber_aged_payable_menu"]',
            run: "click",
        },
        {
            content: "procurar o fornecedor do tour, para a linha ser a encenada",
            trigger: ".o_searchview_input",
            run: "edit Gráfica do Tour",
        },
        {
            content: "e aceitar a primeira sugestao (buscar por fornecedor)",
            trigger: ".o_searchview_autocomplete .o-dropdown-item.focus",
            run: "click",
        },
        {
            content: "a lista chega agrupada por fornecedor",
            trigger: ".o_list_view .o_group_header",
        },
        {
            content: "abrir o primeiro fornecedor",
            trigger: ".o_list_view .o_group_header:first",
            run: "click",
        },
        {
            content: "a linha do documento aparece",
            trigger: ".o_list_view .o_data_row",
        },
        // O caminho de ponta a ponta: marcar a linha e baixar pelo menu
        // Acoes. So a tela prova isto -- a acao de servidor passa por uma
        // checagem de acesso que o metodo, chamado direto no teste de ORM,
        // nao passa; foi assim que o "Erro de acesso" chegou ao prod.
        {
            content: "marcar a linha",
            trigger: ".o_data_row .o_list_record_selector input",
            run: "click",
        },
        {
            content: "abrir o menu Acoes",
            trigger: ".o_control_panel .o_cp_action_menus .o-dropdown",
            run: "click",
        },
        {
            content: "pedir Registrar pagamento",
            trigger: ".o-dropdown--menu .dropdown-item:contains('Register Payment')",
            run: "click",
        },
        {
            content: "o assistente de pagamento abre",
            trigger: ".modal button[name='action_create_payments']",
        },
        {
            content: "fechar o assistente sem pagar",
            trigger: ".modal .btn-close",
            run: "click",
        },
        {
            content: "o botão de pular para o documento está lá",
            trigger: ".o_data_row button[name='action_open_move']",
            run: "click",
        },
        {
            content: "e abriu o lançamento",
            trigger: ".o_form_view .o_breadcrumb",
        },
    ],
});
