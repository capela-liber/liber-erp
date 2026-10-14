/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Meses de fechamento, como ASSISTENTE de contratos: a fileira aparece,
 * dois cliques (jun e dez) marcam o contrato, e a periodicidade lida dos
 * meses vira "Semestral" depois de salvar. Prova o que o ORM não vê: o
 * acesso de leitura aos meses e o widget na tela.
 */
registry.category("web_tour.tours").add("contract_settlement_months_tour", {
    steps: () => [
        {
            trigger: ".o_edlab_month_row label:contains('Jun')",
            content: "Mark June",
            run: "click",
        },
        {
            trigger: ".o_edlab_month_row label:contains('Dec')",
            content: "Mark December",
            run: "click",
        },
        {
            trigger: ".o_form_button_save",
            content: "Save",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_field_widget[name='settlement_periodicity']:contains('Semiannual')",
            content: "The periodicity is read from the months",
        },
    ],
});
