/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Repassar um chamado para a outra empresa, pela tela.
 *
 * O caso é do dono (21/09/2026): "às vezes chega em edlab e precisa ir para
 * n-1". Quem repassa troca a **Equipe**; a empresa é que manda na visão (a
 * ir.rule do chamado filtra por `company_id`), e até aqui ela não seguia a
 * Equipe na troca -- só no nascimento do chamado.
 *
 * O teste de ORM prova o valor gravado. Este tour prova o caminho: que o
 * campo Empresa está desenhado para o perfil, que a Equipe da outra empresa
 * aparece no dropdown, que o onchange muda a empresa na tela antes de
 * salvar, e que salvar não devolve Access Error.
 *
 * O primeiro passo não é cerimônia: com só a casa ligada no seletor de
 * empresas, a `ir.rule` da equipe esconde a equipe da outra empresa e o
 * dropdown responde "No records". Ligar a outra empresa É o caminho.
 *
 * Nada de nome de empresa nos seletores: o tour roda em bancos diferentes,
 * com empresas diferentes. Ele guarda o que o campo mostrava ANTES e exige
 * que mostre outra coisa DEPOIS -- a asserção é a mudança, não o texto.
 */
let empresaAntes = null;

registry.category("web_tour.tours").add("liber_support_repasse_tour", {
    url: "/odoo/action-liber_support.action_support_ticket",
    steps: () => [
        {
            // Primeiro o seletor de empresas, e não por capricho: a
            // ir.rule da equipe filtra pelas empresas LIGADAS. Com só a
            // casa ligada, o dropdown da Equipe responde "No records" e o
            // repasse é impossível — foi o que a captura mostrou.
            trigger: ".o_switch_company_menu button",
            content: "Abrir o seletor de empresas",
            run: "click",
        },
        {
            // Sem nome nem id de empresa: o atendente tem exatamente duas
            // permitidas, então há um só quadradinho vazio para marcar.
            trigger: ".o_switch_company_menu_dropdown " +
                ".o_switch_company_item:has(.fa-square-o) " +
                "div[role='menuitemcheckbox']",
            content: "Ligar a outra empresa",
            run: "click",
        },
        {
            trigger: ".o_switch_company_menu_buttons button.btn-primary",
            content: "Confirmar as duas empresas ligadas",
            run: "click",
            expectUnloadPage: true,
        },
        {
            trigger:
                ".o_kanban_record:contains('Chamado que muda de empresa')",
            content: "Abrir o chamado que chegou na casa errada",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_field_widget[name='team_id']",
            content: "A ficha abriu",
        },
        {
            // Se o perfil não tivesse base.group_multi_company, o campo nem
            // existiria na tela e o repasse seria cego.
            trigger: ".o_form_view .o_field_widget[name='company_id'] input",
            content: "A Empresa está desenhada; guardar o que ela mostra",
            run() {
                empresaAntes = this.anchor.value;
                if (!empresaAntes) {
                    throw new Error("O chamado abriu sem empresa nenhuma");
                }
            },
        },
        {
            trigger: ".o_form_view .o_field_widget[name='team_id'] input",
            content: "Escolher a equipe da outra empresa",
            run: "edit Equipe da Outra Empresa",
        },
        {
            // A equipe da outra empresa só chega até este dropdown se a
            // outra empresa estiver ligada no seletor de empresas.
            trigger:
                ".o-autocomplete--dropdown-item:contains('Equipe da Outra Empresa')",
            content: "A equipe da outra empresa aparece na lista",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_field_widget[name='company_id'] input",
            content: "A Empresa mudou junto, antes de salvar",
            run() {
                if (this.anchor.value === empresaAntes) {
                    throw new Error(
                        "A Empresa continuou em '" + empresaAntes +
                        "' depois de trocar a Equipe");
                }
            },
        },
        {
            // Fechar o dropdown da Equipe antes de mirar o botão: ele fica
            // por cima e o clique no salvar só o dispensa (a captura da
            // primeira tentativa mostrou a lista ainda aberta).
            trigger: ".o_form_sheet",
            content: "Sair do campo",
            run: "click",
        },
        {
            trigger: ".o_form_button_save",
            content: "Salvar o repasse",
            run: "click",
        },
        {
            // Salvou de verdade: com o registro gravado o indicador não
            // oferece mais salvar/descartar. Um Access Error na gravação
            // deixaria o formulário sujo e os botões à vista.
            // `:not(:visible)` e não `.invisible`: o passo exige um
            // elemento VISÍVEL, e aqui o que se quer provar é justamente
            // que ele sumiu (o próprio log do tour deu a dica).
            trigger: ".o_form_status_indicator_buttons:not(:visible)",
            content: "O repasse foi gravado",
        },
    ],
});
