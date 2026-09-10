/** @odoo-module **/
import { registry } from "@web/core/registry";

/* A fila do que falta explicar, na tela.
 *
 * A falta acusada na conferência nasce em Perdas como "a explicar", e é ali
 * -- com tempo, longe do aperto da feira -- que alguém diz o que houve.
 *
 * O que este tour garante: que a tela ABRE na fila (e não agrupada, mostrando
 * cabeçalho e nenhuma linha), que a linha ENTRA EM EDIÇÃO e que o motivo é
 * editável ali mesmo. Já foi diferente: o motivo tinha widget de crachá, que
 * não se edita em lista, e a fila não tinha saída.
 *
 * Onde ele para: o campo de seleção do v19 é um menu próprio (SelectMenu), e
 * dirigi-lo por tour não é confiável -- clique no item não fixa a escolha, e
 * o Enter escolhe o primeiro da lista. Errar aí seria pior do que não testar:
 * o tour ficaria verde gravando OUTRO motivo. O efeito de explicar (a baixa
 * do exemplar, de onde ele estiver) está coberto no ORM, em
 * `test_retorno_curto.py`. */
registry.category("web_tour.tours").add("fair_losses_tour", {
    url: "/odoo/action-liber_fairs.action_event_fair_loss",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "A lista de perdas abre",
        },
        {
            trigger: ".o_data_row .o_data_cell:contains('Título da Perda')",
            content: "A falta do retorno está na fila, e abre para edição",
            run: "click",
        },
        {
            trigger: ".o_selected_row td[name='reason']",
            content: "Entrar no motivo",
            run: "click",
        },
        {
            // O editor existe: é isto que o crachá impedia.
            trigger: ".o_selected_row td[name='reason'] .o_select_menu_toggler",
            content: "O motivo é editável aqui mesmo",
        },
    ],
});
