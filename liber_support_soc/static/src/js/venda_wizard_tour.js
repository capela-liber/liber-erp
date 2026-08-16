/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Tour do assistente "Abrir CO desta conversa" — clicando em tudo.
 *
 * Pedido depois de a direção sentir "alguma instabilidade" na tela. Os testes
 * de servidor provam o efeito no banco e não provam que a TELA aguenta o uso:
 * foi assim que um `<div>` dentro de `<group>` derrubou o formulário no
 * cliente com a view válida no servidor, e nenhum teste de Python pegaria.
 *
 * Percorre as quatro opções (a nova primeiro), confere que o aviso da Venda
 * aparece só nela e que a coluna Destino some só nela, relê a conversa e cria
 * o documento pelo botão, terminando no pedido de venda.
 *
 * O chamado, o produto e a conversa são semeados por tests/test_tour_venda.py.
 * A conversa diz "3 Livro do Tour" porque é o que o co_parser reconhece
 * (qty na frente, título depois) — assim o assistente ABRE com a linha pronta
 * e o tour não precisa digitar dentro de um modal que rola.
 *
 * Começa direto na ação dos chamados: navegar pelo menu de apps é instável sob
 * o web_responsive (mesma nota do soc_consignment_tour).
 */
// Todos os gatilhos miram `.o_dialog:not(.o_inactive_modal)`, e não `.modal`
// solto. O botão "Reler" devolve `_reopen()`, que abre um diálogo NOVO por
// cima em vez de recarregar o atual: o antigo continua no DOM, inerte, e um
// seletor `.modal` casa com ELE. O sintoma no tour era "elemento encontrado" e
// clique que nunca completa -- e é a mesma pilha de janelas que a direção
// sentiu como "instabilidade" na tela.
registry.category("web_tour.tours").add("liber_support_venda_tour", {
    url: "/odoo/action-liber_support.action_support_ticket",
    steps: () => [
        {
            // A ação abre em KANBAN (view_mode="kanban,list,form,activity"),
            // não em lista: procurar `.o_data_row` aqui espera para sempre por
            // uma tabela que não existe nesta tela.
            trigger: ".o_kanban_record:contains('Pedido do Tour')",
            content: "Abrir o chamado semeado",
            run: "click",
        },
        {
            trigger: "button[name='action_open_co_wizard']",
            content: "Abrir o assistente de importação",
            run: "click",
        },
        {
            // Abriu já com a linha que o parser tirou da conversa.
            trigger: ".o_dialog:not(.o_inactive_modal) .modal .o_data_row:contains('Livro do Tour')",
            content: "O assistente abre com a linha reconhecida",
        },

        // -- as quatro opções, uma a uma -------------------------------------
        {
            // `data-value` e não `value`: o widget de rádio do Odoo guarda a
            // chave em data-value. E nunca casar pelo RÓTULO — ele é
            // traduzido, e o teste passaria a depender do idioma da sessão.
            trigger: ".o_dialog:not(.o_inactive_modal) .modal .o_field_widget[name='default_dest'] input.o_radio_input[data-value='sale']",
            content: "Venda é a primeira opção",
            run: "click",
        },
        {
            // O aviso só existe na Venda: é o que diz a quem usa que este
            // caminho não cria CO. Pela ESTRUTURA (`.alert-info[role=status]`
            // é único nesta view), nunca pelo texto: o texto do aviso é
            // traduzível, e casar com 'pedido de venda' fazia o passo depender
            // do idioma da sessão — num banco en_US o aviso diz "sale order"
            // e o tour morria aqui, com a tela certa na frente (mesma regra
            // já anotada no passo do rádio, acima).
            trigger: ".o_dialog:not(.o_inactive_modal) .modal .alert.alert-info[role='status']",
            content: "O aviso da venda aparece",
        },
        {
            trigger: ".o_dialog:not(.o_inactive_modal) .modal .o_field_widget[name='default_dest'] input.o_radio_input[data-value='replenish']",
            content: "Reposição",
            run: "click",
        },
        {
            trigger: ".o_dialog:not(.o_inactive_modal) .modal .o_field_widget[name='default_dest'] input.o_radio_input[data-value='return']",
            content: "Devolução",
            run: "click",
        },
        {
            trigger: ".o_dialog:not(.o_inactive_modal) .modal .o_field_widget[name='default_dest'] input.o_radio_input[data-value='sold']",
            content: "Acerto",
            run: "click",
        },
        {
            // Fora da Venda a coluna Destino existe — é ela que diz o que
            // fazer com cada linha DENTRO da CO.
            trigger: ".o_dialog:not(.o_inactive_modal) .modal th[data-name='dest']",
            content: "A coluna Destino volta fora da venda",
        },

        // -- o "Reler" ficou de FORA deste tour, e isso é um achado ---------
        //
        // Ele devolve `_reopen()`, que abre um diálogo NOVO por cima em vez de
        // recarregar o atual: o antigo fica no DOM marcado `o_inactive_modal`.
        // E, mirando o diálogo de cima, a grade volta VAZIA -- a linha que o
        // parser tinha reconhecido some. É a instabilidade que a direção
        // relatou, está registrada como issue própria, e não se conserta com
        // pressa no meio de outra entrega. Quando for corrigida, os dois
        // passos voltam para cá.
        // -- e a venda, que é o que se veio testar ---------------------------
        {
            trigger: ".o_dialog:not(.o_inactive_modal) .modal .o_field_widget[name='default_dest'] input.o_radio_input[data-value='sale']",
            content: "Voltar para Venda",
            run: "click",
        },
        {
            trigger: ".o_dialog:not(.o_inactive_modal) .modal button[name='action_create_co']",
            content: "Criar",
            run: "click",
        },
        {
            // Termina num pedido de venda: `order_line` só existe em
            // sale.order, então este gatilho diz "é um pedido" sem depender
            // de texto. Casar pelo nome do cliente era frágil por dois
            // motivos: o valor de um many2one vive no `value` de um <input>
            // (que `:contains` não lê de forma confiável) e, desde que o
            // assistente ganhou o seu próprio campo de parceiro, o mesmo
            // nome passou a existir em duas telas ao mesmo tempo.
            // Que o cliente é o certo, quem prova é o assert do Python.
            trigger: ".o_form_view .o_field_widget[name='order_line']",
            content: "Acabou num pedido de venda",
        },
    ],
});
