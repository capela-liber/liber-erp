/** @odoo-module **/
import { registry } from "@web/core/registry";

/* O caminho inteiro da feira, na tela, com o perfil de quem a opera.
 *
 * Despachar -> conferir a chegada em Recebimentos -> contar a mesa e fechar
 * o dia. É o percurso que a equipe faz de verdade, e é justamente o que o
 * teste de ORM não enxerga: o direito de LER stock.picking na lista de
 * Recebimentos, o botão de cabeçalho que só aparece com linhas marcadas, a
 * seção do menu dentro do aplicativo e a coluna editável do fechamento.
 *
 * Os passos casam com os rótulos em PORTUGUÊS porque o usuário do tour nasce
 * em pt_BR: é assim que a tela chega para quem trabalha a feira. */
registry.category("web_tour.tours").add("fair_full_tour", {
    url: "/odoo/action-liber_fairs.action_event_fair",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "A lista de feiras abre para o perfil",
        },
        {
            trigger: ".o_data_row .o_data_cell:contains('Feira do Tour Completo')",
            content: "Abrir a feira do tour",
            run: "click",
        },
        {
            trigger: ".o_form_view_container",
            content: "O formulário da feira abriu",
        },
        {
            // pelo NAME do método: rótulo muda com a tradução, método não.
            trigger: "button[name='action_ship']",
            content: "Despachar a carga para a praça",
            run: "click",
        },
        {
            // Retorno só existe com a feira em curso: é a prova de que o
            // despacho pegou, sem depender do texto do statusbar.
            trigger: "button[name='action_return']",
            content: "A feira está em curso",
        },
        {
            trigger: ".o_menu_sections a:contains('Recebimentos')",
            content: "Ir para Recebimentos, onde a praça confere",
            run: "click",
        },
        {
            trigger: ".o_list_view .o_data_row",
            content: "A carga a conferir está na lista",
        },
        {
            trigger: "thead .o_list_record_selector input",
            content: "Marcar tudo o que chegou",
            run: "click",
        },
        {
            trigger: "button[name='action_fair_check']",
            content: "Um ok geral: chegou",
            run: "click",
        },
        {
            // A lista nasce filtrada em "A conferir": conferido, some. A
            // conferência é POR LINHA, e o que se prova aqui é que a carga
            // DESTA feira saiu da fila -- outras feiras da casa podem ter
            // carga esperando, e isso não é problema deste tour.
            trigger: ".o_list_view:not(:has(.o_data_cell:contains('Feira do Tour Completo')))",
            content: "A carga desta feira saiu da fila",
        },
        {
            trigger: ".o_menu_sections a:contains('Fechamentos diários')",
            content: "Ir para o fechamento do dia",
            run: "click",
        },
        {
            // A lista de fechamentos abre AGRUPADA POR FEIRA e filtrada nas
            // que estão na praça: com três feiras rodando, o que existe na
            // tela é cabeçalho de grupo, não linha.
            trigger: ".o_group_header:contains('Feira do Tour Completo')",
            content: "Abrir o grupo da feira do tour",
            run: "click",
        },
        {
            trigger: ".o_data_row .o_data_cell",
            content: "Abrir o dia",
            run: "click",
        },
        {
            trigger: "button[name='action_fill']",
            content: "Trazer a mesa para a contagem",
            run: "click",
        },
        {
            trigger: ".o_field_x2many_list .o_data_row",
            content: "A mesa veio, título a título",
        },
        {
            trigger: ".o_data_row:first-child td[name='qty_counted']",
            content: "Corrigir para baixo o que foi vendido",
            run: "click",
        },
        {
            trigger: ".o_data_row:first-child td[name='qty_counted'] input",
            content: "Contou seis",
            run: "edit 6",
        },
        {
            trigger: "button[name='action_close']",
            content: "Fechar o dia",
            run: "click",
        },
        {
            // Prova de verdade: com o dia fechado, os botões de operar o dia
            // somem da barra. Um seletor que casasse com o formulário
            // qualquer terminaria o tour ANTES de a gravação acontecer.
            trigger: ".o_form_view:not(:has(button[name='action_close']))",
            content: "O dia fechou",
        },
    ],
});
