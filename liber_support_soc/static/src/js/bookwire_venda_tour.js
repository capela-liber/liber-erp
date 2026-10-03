/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Tour do relatório da Bookwire: do chamado de Atendimento ao pedido de venda.
 *
 * Todo mês a Bookwire manda por e-mail um ZIP com o relatório de vendas; o
 * e-mail vira chamado. O caminho que este tour prova é o do dia a dia de quem
 * lança o digital: abrir o chamado, "Importar", ver que o assistente
 * reconheceu o relatório (aviso próprio e coluna de preço, que não existem na
 * venda comum) e criar o pedido de venda.
 *
 * Entra com um usuário Comercial Assistente + Atendimento, criado em
 * tests/test_tour_bookwire.py -- não o admin, que passa em tudo. O valor, a
 * empresa, a equipe e a ausência de desconto são conferidos no Python.
 *
 * Seletores por estrutura (`role`, `name`, `data-name`), nunca por texto
 * traduzível -- mesma regra do liber_support_venda_tour.
 */
registry.category("web_tour.tours").add("liber_support_bookwire_tour", {
    url: "/odoo/action-liber_support.action_support_ticket",
    steps: () => [
        {
            trigger: ".o_kanban_record:contains('Bookwire - Sales Report - 8/2026')",
            content: "Abrir o chamado do relatório",
            run: "click",
        },
        {
            trigger: "button[name='action_open_co_wizard']",
            content: "Importar",
            run: "click",
        },
        {
            // Abre com a planilha convertida (a mais nova), como o chamado
            // 2129 do staging. Escolher o ZIP no campo é o que relê a grade
            // NA TELA -- o caminho que quebrava ao salvar.
            trigger: ".o_dialog:not(.o_inactive_modal) .modal .o_field_widget[name='attachment_id'] input",
            content: "Escolher o ZIP da Bookwire no campo do anexo",
            run: "edit A-1",
        },
        {
            trigger: ".o-autocomplete--dropdown-item:contains('.zip')",
            content: "O ZIP aparece na lista",
            run: "click",
        },
        {
            // O aviso do relatório: só aparece quando o anexo é a Bookwire.
            trigger: ".o_dialog:not(.o_inactive_modal) .modal .alert.alert-success[role='note']",
            content: "O assistente reconheceu o relatório da Bookwire",
        },
        {
            trigger: ".o_dialog:not(.o_inactive_modal) .modal th[data-name='price_unit']",
            content: "A coluna de preço do relatório aparece",
        },
        {
            trigger: ".o_dialog:not(.o_inactive_modal) .modal .o_data_row:contains('Audiolivro do Tour')",
            content: "As linhas vieram do CSV dentro do ZIP",
        },
        {
            trigger: ".o_dialog:not(.o_inactive_modal) .modal button[name='action_create_co']",
            content: "Criar o pedido",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_field_widget[name='order_line'] .o_data_row",
            content: "Acabou num pedido de venda com linhas",
        },
    ],
});
