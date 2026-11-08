/** @odoo-module **/

/**
 * A coluna pela tela: entrar em Produção agenda o job como atividade; seguir
 * para Feito não a tira. Prova que a barra de estágios do formulário dispara e
 * que a atividade aparece no chatter, no perfil de usuário de projeto.
 */
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("stage_jobs_tour", {
    steps: () => [
        {
            content: "para a coluna Produção",
            trigger: ".o_form_view .o_statusbar_status button:contains(Producao)",
            run: "click",
        },
        {
            content: "a atividade do job apareceu no chatter",
            trigger: ".o-mail-Chatter .o-mail-Activity:contains(Capa)",
        },
        {
            content: "para a coluna Feito",
            trigger: ".o_form_view .o_statusbar_status button:contains(Feito)",
            run: "click",
        },
        {
            content: "a coluna Feito está ativa",
            trigger: ".o_form_view .o_statusbar_status button.o_arrow_button_current:contains(Feito)",
        },
        {
            content: "e a atividade continua lá",
            trigger: ".o-mail-Chatter .o-mail-Activity:contains(Capa)",
        },
    ],
});
