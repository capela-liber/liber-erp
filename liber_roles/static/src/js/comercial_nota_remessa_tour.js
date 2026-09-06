/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * O "Criar nota" do Pedido C, no perfil de quem clica.
 *
 * Bloqueio de produção de 26/08/2026: o C08577 (reposição de consignação da
 * n-1, Clara Crocodilo Edições) recusou o "Criar nota" com
 *
 *     A conta bancária da sua empresa não é confiável. Peça a um administrador
 *     ou a alguém com direitos de aprovação para verificá-la.
 *
 * Uma mensagem sobre banco num documento que não tem banco: consignação não
 * movimenta dinheiro, é valor de estoque que continua nosso na prateleira do
 * outro. O core do Odoo carimba a conta de recebimento da empresa em TODA
 * fatura de cliente e depois recusa o post se ela não estiver avalizada; o
 * conserto (liber_nfe_remessa) é a remessa não levar conta nenhuma.
 *
 * O teste de ORM daquele módulo prova o mecanismo. Este tour prova a TELA, no
 * perfil real -- que é onde o erro apareceu, e como uma caixa de diálogo. O
 * mundo (livraria com contrato, livro expedido, posição fiscal ligada e TODAS
 * as contas da empresa sem aval) é semeado por tests/test_tour_comercial.py.
 *
 *     odoo.startTour("comercial_nota_remessa_tour")
 */
registry.category("web_tour.tours").add("comercial_nota_remessa_tour", {
    // Direto na ação: o menu de apps é instável sob web_responsive.
    url: "/odoo/action-liber_soc_moves.action_consignment_sale_order",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "A lista de Pedidos de consignação abre para o gerente",
        },
        {
            trigger: ".o_data_row:contains('Livraria da Nota') td.o_data_cell:not(.o_list_record_selector)",
            content: "Abre o Pedido C que já expediu a carga",
            run: "click",
        },
        {
            trigger: ".o_form_view_container",
            content: "O Pedido C abre no formulário",
        },
        {
            // O CLIQUE DO ACIDENTE. Sem o conserto, aqui sobe a caixa
            // "Operação inválida" falando de conta bancária.
            trigger: "button[name='action_generate_remessa_note']",
            content: "Criar nota: é este clique que falava de banco",
            run: "click",
        },
        {
            // O botão "Criar nota" some quando remessa_note_move_id existe:
            // a ausência dele É a prova de que a nota nasceu. Este passo é o
            // que pega a regressão -- se a caixa "Operação inválida" subir, o
            // botão continua lá e o tour estoura aqui.
            //
            // Não se põe um `body:not(:has(.modal))` ANTES deste: a caixa de
            // erro leva um instante para renderizar, e o passo passava no vão
            // entre o clique e o modal. Foi o que mascarou a primeira rodada
            // (26/08/2026), até a captura em /tmp/odoo_tests mostrar o diálogo
            // que o tour jurava não existir.
            trigger: ".o_form_view_container:not(:has(button[name='action_generate_remessa_note']))",
            content: "A nota de remessa saiu -- o botão cumpriu e sumiu",
        },
        {
            // Agora sim: a esta altura, qualquer caixa já teria subido.
            trigger: "body:not(:has(.modal))",
            content: "E nenhuma caixa de erro subiu no caminho",
        },
    ],
});
