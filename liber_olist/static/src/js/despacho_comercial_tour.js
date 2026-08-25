/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * O comercial despacha (24/08/2026).
 *
 * O tour irmão (`olist_despacho_tour`) prova que a fila ABRE para um perfil
 * comum, que só lê. Este prova o ato: marcar o pedido e clicar em Despachar,
 * logado como Assistente comercial — o perfil que ganhou o direito hoje.
 *
 * Vale um clique porque o caminho atravessa quatro donos: a venda, a fatura
 * do XML, a transferência na caixa Marketplaces e o anexo. O teste de ORM
 * mede cada um; só a tela mede o botão. E é a tela que dizia "Você não tem
 * permissões para criar registros de Espelho de pedido do Olist".
 *
 * Ao vivo, no console (modo desenvolvedor):
 *     odoo.startTour("olist_despacho_comercial_tour")
 */
registry.category("web_tour.tours").add("olist_despacho_comercial_tour", {
    url: "/odoo/action-liber_olist.action_olist_fila",
    steps: () => [
        {
            trigger: ".o_data_row td:contains('TOUR-C1')",
            content: "O pedido está na fila do comercial",
        },
        {
            trigger: ".o_data_row:first .o_list_record_selector input",
            content: "Marcar o pedido",
            run: "click",
        },
        {
            // Pelo `name`, não pelo texto: "Despachar" também é o nome do
            // menu e o da própria ação — três acertos para o mesmo seletor.
            trigger: "button[name='action_import_selected']",
            content: "Despachar",
            run: "click",
        },
        {
            // Sucesso abre a VENDA criada. Se faltasse um direito, o que
            // apareceria aqui seria a notificação de importação parcial — e
            // o passo cairia, que é exatamente o ponto do tour.
            trigger: ".o_form_view_container [name='partner_id']",
            content: "A venda abre: o despacho coube no perfil",
        },
    ],
});
