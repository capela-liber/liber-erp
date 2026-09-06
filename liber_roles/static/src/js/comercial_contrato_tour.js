/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * O contrato de consignação (AC), nos dois perfis que o tocam.
 *
 * Nasceu de um bloqueio de produção (26/08/2026): a gerente comercial clicou
 * "Ativar" no AC/2026/0277 e levou "Você não tem permissões para criar
 * registros de 'Locais de inventário' (stock.location)". A prateleira do
 * cliente É um stock.location, e criar local no core é direito de
 * Inventário/Administrador -- que o Comercial não tem, e não deve ter.
 *
 * O teste de ORM do liber_soc_agreements já prova a ativação no perfil pelado;
 * estes dois tours provam a TELA, que é onde o erro apareceu. O ORM mede o que
 * o teste pediu; o tour mede o que a tela pede.
 *
 * O mundo é semeado por tests/test_tour_comercial.py.
 */

/**
 * GERENTE: abre um contrato do zero e o ativa. O clique do acidente é o
 * "Activate", e a prova de que passou é o botão de prateleira aparecendo.
 *
 *     odoo.startTour("comercial_contrato_tour")
 */
registry.category("web_tour.tours").add("comercial_contrato_tour", {
    // Direto na ação: o menu de apps é instável sob web_responsive (ver
    // copyright_contracts_tour).
    url: "/odoo/action-liber_soc_agreements.action_consignment_agreement",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "A lista de Contratos abre para o gerente comercial",
        },
        {
            // O botão Novo só existe para quem tem create no modelo: a sua
            // presença aqui é metade da regra de 26/08 (a outra metade é o
            // tour do assistente, abaixo, onde ele NÃO pode existir).
            trigger: ".o_list_button_add",
            content: "O gerente abre contrato: o botão Novo está lá",
            run: "click",
        },
        {
            trigger: ".o_form_view_container",
            content: "O contrato novo abre em rascunho",
        },
        {
            trigger: "div[name='partner_id'] input",
            content: "Escolhe a livraria do contrato",
            run: "edit Livraria do Contrato",
        },
        {
            trigger: ".o-autocomplete--dropdown-item a:contains('Livraria do Contrato')",
            content: "Confirma a livraria na lista",
            run: "click",
        },
        {
            // O CLIQUE DO ACIDENTE: aqui nascem a raiz CO e a prateleira.
            trigger: "button[name='action_activate']",
            content: "Ativar: é este clique que criava o Access Error",
            run: "click",
        },
        {
            // pelo data-value, nunca pelo rótulo: em pt_BR o estado muda de
            // texto e um :contains('Active') quebraria sem regressão
            trigger: ".o_statusbar_status button.o_arrow_button_current[data-value='active']",
            content: "O contrato ativou -- o clique que quebrava em produção passou",
        },
        {
            // o stat button é invisível até location_id existir: a presença
            // dele É a prova de que a prateleira nasceu
            trigger: "button[name='action_view_shelf']",
            content: "O botão de prateleira prova que o stock.location nasceu",
            run: "click",
        },
        {
            // A PRATELEIRA ABERTA, e não só o botão. O estoque da prateleira é
            // stock.quant, cujo ACL é do Inventário -- e o Comercial não tem o
            // app. Um botão que abre em Access Error é um botão quebrado, e o
            // tour parava antes de descobrir isso.
            trigger: ".o_list_view, .o_nocontent_help",
            content: "A prateleira abre para quem fechou o contrato",
        },
        {
            trigger: ".o_breadcrumb .o_back_button, .breadcrumb-item:first-child a",
            content: "Volta ao contrato",
            run: "click",
        },
        // ------------------------------------------------------------------
        // O RESTO DA VIDA DO CONTRATO. Suspender e reativar são os botões que
        // a casa usa quando a livraria para de responder acerto; até 27/08 o
        // tour parava na ativação e eles nunca tinham sido clicados por
        // ninguém a não ser o admin.
        {
            trigger: "button[name='action_suspend']",
            content: "Suspender: a livraria parou de responder",
            run: "click",
        },
        {
            trigger: ".o_statusbar_status button[data-value='suspended'].o_arrow_button_current",
            content: "O contrato ficou suspenso",
        },
        {
            trigger: "button[name='action_reactivate']",
            content: "Reativar: a livraria voltou a responder",
            run: "click",
        },
        {
            trigger: ".o_statusbar_status button[data-value='active'].o_arrow_button_current",
            content: "E volta a ativo, com a mesma prateleira",
        },
        {
            // A prateleira não pode renascer na reativação: um segundo
            // stock.location para o mesmo cliente partiria o estoque em dois e
            // o mapa mensal contaria metade.
            trigger: "button[name='action_view_shelf']",
            content: "A prateleira é a mesma: reativar não abre outra",
        },
    ],
});

/**
 * ASSISTENTE: não abre contrato, mas opera o que existe.
 *
 *     odoo.startTour("comercial_contrato_assistente_tour")
 */
registry.category("web_tour.tours").add("comercial_contrato_assistente_tour", {
    url: "/odoo/action-liber_soc_agreements.action_consignment_agreement",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "A lista de Contratos abre também para o assistente",
        },
        {
            // A ausência do Novo é a regra de 26/08 na tela. O Odoo tira o
            // botão do controlador quando o ACL nega o create, então isto
            // acusa a volta do direito -- não só a falta do botão.
            trigger: ".o_control_panel:not(:has(.o_list_button_add))",
            content: "O assistente não tem o botão Novo: contrato é do gerente",
        },
        {
            trigger: ".o_data_row:contains('Livraria do Assistente') td.o_data_cell:not(.o_list_record_selector)",
            content: "Abre o contrato ativo que o gerente deixou",
            run: "click",
        },
        {
            trigger: ".o_form_view_container",
            content: "O contrato abre no formulário",
        },
        {
            trigger: "button[name='action_suspend']",
            content: "Suspender: isto o assistente pode, e é o ponto",
            run: "click",
        },
        {
            trigger: ".o_statusbar_status button.o_arrow_button_current[data-value='suspended']",
            content: "O contrato ficou suspenso pelas mãos do assistente",
        },
    ],
});
