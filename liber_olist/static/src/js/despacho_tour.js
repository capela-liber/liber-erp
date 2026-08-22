/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * A fila de despacho lida pelo perfil de todo dia (22/08/2026).
 *
 * O ORM prova o direito; este tour prova a CHEGADA: que a fila Despachar
 * renderiza para um funcionário comum (leitura, por desenho — quem importa é
 * a gerência), que o pedido aparece com a situação do XML no badge, e que a
 * ficha dele abre. É a tela quem pede campos que o teste de ORM nunca pediu
 * — foi assim que dois Access Error apareceram no Editorial das compras.
 *
 * Ao vivo, no console do navegador (modo desenvolvedor):
 *     odoo.startTour("olist_despacho_tour")
 * ou pelo tests/test_tour_despacho.py.
 */
registry.category("web_tour.tours").add("olist_despacho_tour", {
    // Direto na ação, como nos tours do liber_roles: o que se testa é a
    // tela, não a animação da gaveta de apps.
    url: "/odoo/action-liber_olist.action_olist_fila",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "A fila Despachar abre para o perfil comum",
        },
        {
            trigger: ".o_data_row td:contains('TOUR-900')",
            content: "O pedido semeado está na fila",
        },
        {
            trigger: ".o_data_row .o_field_badge",
            content: "A situação do XML aparece no badge",
        },
        {
            trigger: ".o_data_row:first td.o_data_cell:not(.o_list_record_selector)",
            content: "Abrir a ficha do pedido",
            run: "click",
        },
        {
            trigger: ".o_form_view_container",
            content: "A ficha abre: ler é o que este perfil veio fazer",
        },
        {
            // Sem `.o_field_widget`: formulário só-leitura não põe o wrapper
            // de edição (lição do tour do Editorial).
            trigger: ".o_form_view_container [name='numero']",
            content: "O número do pedido lê",
        },
    ],
});
