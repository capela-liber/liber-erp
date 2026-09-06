/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Tour do "Importar" na CO — o atendimento ATIVO pela tela.
 *
 * A regra da casa (22/08) diz o porquê deste arquivo existir ao lado dos
 * testes de ORM: o ORM mede o que o teste pediu, a tela mede o que a tela
 * pede. Aqui há duas coisas que só a tela prova, e as duas já mordram a casa
 * antes noutros módulos:
 *
 * 1. o ACL. O assistente nasceu com acesso só para o `group_support_user`, e
 *    quem opera consignação pode não ser do Atendimento — o teste loga como
 *    COMERCIAL, não como admin (admin passa em tudo e não prova nada sobre o
 *    perfil);
 * 2. o botão herdado. Ele entra por `position="after"` num botão do
 *    `liber_soc_settlement`; se aquele botão for renomeado lá, a view quebra
 *    na carga e nenhum teste de Python percebe.
 *
 * A CO, a livraria e a conversa são semeadas por tests/test_tour_import_co.py.
 * A conversa diz "3 Livro do Ativo" porque é o formato que o co_parser
 * reconhece (quantidade na frente, título depois) — assim o assistente ABRE
 * com a linha pronta e o tour não digita dentro de um modal que rola.
 *
 * Os gatilhos miram `.o_dialog:not(.o_inactive_modal)` pelo mesmo motivo
 * anotado no venda_wizard_tour: `_reopen()` empilha diálogos, e um seletor
 * `.modal` solto casa com o de baixo, inerte.
 */
registry.category("web_tour.tours").add("liber_support_import_na_co_tour", {
    url: "/odoo/action-liber_soc_settlement.action_consignment_settlement",
    steps: () => [
        {
            trigger: ".o_kanban_record:contains('Livraria do Ativo')",
            content: "Abrir a CO da livraria",
            run: "click",
        },
        {
            // O botão do atendimento ativo, no cabeçalho, ao lado do Mapa.
            trigger: "button[name='action_open_co_wizard']",
            content: "Importar a resposta da livraria",
            run: "click",
        },
        {
            // Abriu já com a linha que o parser tirou da conversa da CO.
            trigger: ".o_dialog:not(.o_inactive_modal) .modal .o_data_row:contains('Livro do Ativo')",
            content: "O assistente abre com a linha reconhecida",
        },
        {
            // O aviso que só existe nesta âncora: as linhas entram NESTA CO.
            // Pela ESTRUTURA e pela posição, nunca pelo texto — o texto é
            // traduzível e o passo passaria a depender do idioma da sessão.
            trigger: ".o_dialog:not(.o_inactive_modal) .modal .alert.alert-info[role='status']",
            content: "O aviso de que as linhas entram nesta CO",
        },
        {
            trigger: ".o_dialog:not(.o_inactive_modal) .modal button[name='action_create_co']",
            content: "Criar",
            run: "click",
        },
        {
            // Termina de volta NA CO, com a linha dentro dela. `line_ids` na
            // ficha da consignação é o que diz "é a CO, e ela recebeu".
            trigger: ".o_form_view .o_field_widget[name='line_ids'] .o_data_row:contains('Livro do Ativo')",
            content: "A linha caiu na própria CO",
        },
    ],
});
