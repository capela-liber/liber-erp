/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Licenciamento, como GERENTE de contratos com Faturamento (não admin):
 * do contrato, o botão "Licensing" abre as faturas do contrato; o New
 * padrão traz a fatura pronta (produto, conta e o analítico do autor na
 * linha); só se escolhe o licenciado e o valor, e confirma. Prova o que o
 * ORM não vê: o botão na tela, a lista abrindo com o direito do perfil e
 * a fatura nascendo com os padrões do contrato.
 */
registry.category("web_tour.tours").add("copyright_licensing_tour", {
    steps: () => [
        {
            // Com Missões e Chamados na caixa, a 1366px o "Licensing" cai
            // dentro do "More" -- o mesmo tropeço do tour das vendas legadas.
            trigger: ".o-form-buttonbox .o_button_more",
            content: "Unfold the rest of the button box",
            run: "click",
        },
        {
            trigger: "button[name='action_view_license_invoices']",
            content: "Open the contract's licensing invoices",
            run: "click",
        },
        {
            trigger: ".o_list_view .o_list_button_add",
            content: "New licensing invoice",
            run: "click",
        },
        {
            trigger: ".o_form_view div[name='invoice_line_ids'] .o_data_row td[name='product_id']:contains('Rights licensing')",
            content: "The line arrives with the licensing product",
        },
        {
            trigger: ".o_form_view div[name='partner_id'] input",
            content: "Pick the licensee",
            run: "edit Editora Didática Tour",
        },
        {
            trigger: ".o-autocomplete--dropdown-item:contains('Editora Didática Tour')",
            run: "click",
        },
        {
            trigger: "div[name='invoice_line_ids'] .o_data_row:first td[name='price_unit']",
            content: "Type the licence amount",
            run: "click",
        },
        {
            trigger: "div[name='invoice_line_ids'] .o_data_row:first td[name='price_unit'] input",
            run: "edit 1000",
        },
        {
            trigger: ".o_form_button_save",
            content: "Save",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_form_saved",
        },
        {
            trigger: ".o_form_view button[name='action_post']",
            content: "Confirm the invoice",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_statusbar_status button.o_arrow_button_current:contains('Posted')",
            content: "The licence is posted",
        },
    ],
});
