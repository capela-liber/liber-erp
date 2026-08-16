/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Abrir a ficha de um chamado que JÁ TEM documento vinculado.
 *
 * Nasceu de "não consigo abrir chamados da Catavento" (13/08/2026). Levantados
 * os dados do staging, a Catavento não tinha nada de especial como cliente: o
 * que ela tinha, e mais ninguém, era ser dona dos **três únicos chamados do
 * banco com pedido de venda vinculado** -- de 1.884. E dois deles são também
 * dois dos três com CO vinculada.
 *
 * O que só aparece nesses três é o botão do topo (`oe_button_box`), escondido
 * por `invisible="not sale_order_id"`. Ou seja: a ficha que ninguém conseguia
 * abrir era a única que mandava o cliente desenhar aquele botão.
 *
 * Este tour semeia exatamente essa condição e abre a ficha. Ele não afirma
 * nada sobre o conteúdo: se a tela quebrar no cliente, o HttpCase falha pelo
 * erro de console, que é o sintoma que se está perseguindo -- o servidor
 * respondia 200 em tudo, e o log do staging não tinha uma linha de erro.
 */
registry.category("web_tour.tours").add("liber_support_ficha_vinculada_tour", {
    url: "/odoo/action-liber_support.action_support_ticket",
    steps: () => [
        {
            trigger: ".o_kanban_record:contains('Chamado com vínculos')",
            content: "Abrir o chamado que tem pedido e CO",
            run: "click",
        },
        {
            // Chegou na ficha: se o cliente tivesse quebrado ao desenhar o
            // botão, não haveria formulário nenhum aqui.
            trigger: ".o_form_view .o_field_widget[name='partner_id']",
            content: "A ficha abriu",
        },
        {
            // Sem `.oe_button_box` no seletor: essa classe é do ARCH, e o
            // que o cliente desenha é `.o_button_box`. Mirar a classe do
            // arch faz o passo falhar com a tela perfeita na frente.
            trigger: ".o_form_view button[name='action_open_sale_order']",
            content: "O botão do pedido está desenhado",
        },
        {
            trigger: ".o_form_view button[name='action_open_settlement']",
            content: "O botão da CO está desenhado",
        },
    ],
});
