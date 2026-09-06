/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * O Pedido C na tela: a remessa que enche a prateleira, e as duas recusas.
 *
 * Escrito em 24/08/2026, depois que o C000 foi liberado para o Gerente
 * Comercial abrir consignações e a equipe percebeu que "o estoque que foi
 * criado até agora não foi para a prateleira". Eram dois buracos no mesmo
 * documento:
 *
 *   - a remessa ia para "Clientes" (o livro saía do estoque e não entrava em
 *     prateleira nenhuma: mapa vazio, acerto sem o que cobrar);
 *   - o pedido confirmava para cliente sem contrato e para contrato suspenso.
 *
 * SÃO TRÊS TOURS, e não um com três atos, porque cada um começa numa tela
 * limpa: um tour longo teria de voltar pela trilha entre um caso e outro, e é
 * navegação que quebra sem provar nada. Quem os encadeia é o
 * tests/test_tour_pedido_c.py, que roda os três seguidos.
 *
 * A DIVISÃO DE TRABALHO com o teste de ORM é de propósito. Aqui se prova o que
 * só a tela mostra: que o perfil alcança a lista de Pedidos de consignação,
 * que o contrato aparece sozinho no formulário, que o botão de entrega existe
 * e abre, e que a recusa chega como caixa de diálogo com o motivo escrito --
 * não como um silêncio. O destino do movimento e a prateleira cheia quem mede
 * é o test_pedido_c_prateleira.py, com o motor: contar quant na tela exigiria
 * o "Locais de armazenamento" ligado, que é configuração de cada base.
 *
 * Os clientes ("Livraria ...") e os Pedidos C em rascunho são semeados pelo
 * teste. Rodar à mão exige semear antes.
 */

const LISTA_PEDIDOS_C =
    "/odoo/action-liber_soc_moves.action_consignment_sale_order";

/**
 * Os passos comuns: abrir o Pedido C de `livraria`, que o teste semeou em
 * rascunho -- como a Operação de Consignação o cria.
 *
 * Até 06/09/2026 este bloco clicava em "Novo" e digitava o pedido. Não há
 * mais "Novo" nesta lista (`create: False` na ação): o Pedido C nasce da CO,
 * e só dela. Um Pedido C digitado aqui era um documento sem operação por
 * trás, e foi assim que 51 "reposições" entraram à mão em agosto. O primeiro
 * passo prova exatamente isso -- que o botão não está na tela.
 */
function abrirPedido(livraria) {
    return [
        {
            trigger: ".o_list_view:not(:has(.o_list_button_add))",
            content: "A lista de Pedidos C não oferece 'Novo': o Pedido C nasce da CO",
        },
        {
            trigger: `.o_data_row:contains('${livraria}') td.o_data_cell:not(.o_list_record_selector)`,
            content: "Abre o Pedido C que a operação criou",
            run: "click",
        },
        {
            trigger: ".o_form_view_container",
            content: "O Pedido C abre no formulário",
        },
    ];
}

/** Caminho feliz: contrato ativo, remessa criada, entrega alcançável. */
registry.category("web_tour.tours").add("pedido_c_prateleira_tour", {
    url: LISTA_PEDIDOS_C,
    steps: () => [
        ...abrirPedido("Livraria do Pedido C"),
        {
            // O contrato do cliente aparece SOZINHO no formulário: é ele que
            // decide para qual prateleira a remessa vai. Casar por "AC/" e não
            // pelo número inteiro -- a sequência muda conforme a base.
            trigger: ".o_field_widget[name='consignment_agreement_id']:contains('AC/')",
            content: "O contrato do cliente foi resolvido no próprio pedido",
        },
        {
            trigger: "button[name='action_confirm']",
            content: "Confirmar: aqui a casa cobra o contrato ativo",
            run: "click",
        },
        {
            // data-value, não o rótulo: em pt_BR ele é "Pedido de venda", e um
            // :contains('Sales Order') quebraria em base traduzida.
            trigger: ".o_statusbar_status button.o_arrow_button_current[data-value='sale']",
            content: "Confirmado",
        },
        {
            trigger: "button[name='action_view_delivery']",
            content: "A remessa existe e o comercial a alcança",
            run: "click",
        },
        {
            // COM/OUT é a série da remessa de consignação. Se ela tivesse
            // saído na entrega genérica do armazém, aqui estaria WH/OUT --
            // foi assim que o defeito do tipo de operação apareceu no C00003.
            trigger: ".o_breadcrumb:contains('COM/OUT')",
            content: "A remessa saiu na série da consignação, não na da venda",
        },
    ],
});

/** Recusa 1: cliente sem contrato de consignação. */
registry.category("web_tour.tours").add("pedido_c_sem_contrato_tour", {
    url: LISTA_PEDIDOS_C,
    steps: () => [
        ...abrirPedido("Livraria sem Contrato"),
        {
            // Que o campo do contrato ficou VAZIO quem confere é o teste, em
            // `assertFalse(pedido.consignment_agreement_id)`. Aqui houve uma
            // tentativa de `:not(:contains('AC/'))` e o motor de seletores do
            // tour não a sustenta -- o passo falhava com o campo corretamente
            // vazio na tela (a captura de 24/08 mostrava exatamente isso).
            // Ausência é o que a tela mede mal e o ORM mede exato.
            trigger: "button[name='action_confirm']",
            content: "Confirmar sem contrato",
            run: "click",
        },
        {
            // `.o_dialog:not(.o_inactive_modal)` e não `.modal` cru: o Odoo
            // mantém no DOM os diálogos que ficaram atrás, e o seletor curto
            // casaria com um deles (ver venda_wizard_tour do liber_support_soc).
            trigger: ".o_dialog:not(.o_inactive_modal) .modal-body:contains('has no consignment agreement')",
            content: "A recusa vem escrita, e diz o que fazer: abrir o contrato",
        },
        {
            trigger: ".o_dialog:not(.o_inactive_modal) .modal-footer button",
            run: "click",
        },
        {
            trigger: ".o_statusbar_status button.o_arrow_button_current[data-value='draft']",
            content: "O pedido ficou onde estava: nada saiu do armazém",
        },
    ],
});

/** Recusa 2: o contrato existe, mas está suspenso. */
registry.category("web_tour.tours").add("pedido_c_suspenso_tour", {
    url: LISTA_PEDIDOS_C,
    steps: () => [
        ...abrirPedido("Livraria Suspensa"),
        {
            trigger: "button[name='action_confirm']",
            run: "click",
        },
        {
            // "is Suspended" e não "cannot be confirmed": as duas recusas
            // terminam com a segunda frase, e o tour tem de distinguir QUAL
            // delas apareceu -- senão o caso do suspenso passaria verde
            // exibindo a mensagem do sem-contrato.
            trigger: ".o_dialog:not(.o_inactive_modal) .modal-body:contains('is Suspended')",
            content: "A suspensão segura a remessa, que é para isso que ela existe",
        },
        {
            trigger: ".o_dialog:not(.o_inactive_modal) .modal-footer button",
            run: "click",
        },
        {
            trigger: ".o_statusbar_status button.o_arrow_button_current[data-value='draft']",
            content: "Continua em rascunho",
        },
    ],
});
