/** @odoo-module **/

/**
 * O caminho de tela das Subtarefas por prioridade, no perfil do gerente de
 * projeto (não o admin).
 *
 * O teste de ORM prova a cópia; este prova que a opção mora ao lado das
 * Tarefas recorrentes, que ela traz só o link (nada de escolher modelo por
 * estrela), e que o link abre só os modelos daquele projeto, com a estrela,
 * o responsável e a coluna de cada um -- cada card ali é uma subtarefa.
 *
 * A sessão roda em inglês (como os tours do `liber_roles`): os textos
 * procurados são a fonte que o `pt_BR.po` traduz.
 */
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("priority_template_tour", {
    steps: () => [
        {
            content: "aba Definições do projeto",
            trigger: ".o_notebook_headers .nav-link:contains(Settings)",
            run: "click",
        },
        {
            content: "desligada, a opção não mostra o link",
            trigger: ".o_form_view:not(:has(button[name=action_open_priority_templates]))",
        },
        {
            content: "a opção mora no Gerenciamento de tarefas, ao lado das recorrentes",
            trigger: ".o_setting_box:has(div[name=allow_recurring_tasks]) ~ .o_setting_box div[name=allow_priority_templates] input",
            run: "click",
        },
        {
            // Sem salvar antes: o link salva e vai, no primeiro clique.
            content: "marcada, só o link Modelos de tarefa",
            trigger: ".o_form_view:not(:has(div[name=priority_template_medium_id])) button[name=action_open_priority_templates]",
            run: "click",
        },
        {
            content: "a lista traz só os modelos deste projeto, com a estrela de cada um",
            trigger: ".o_list_view:not(:has(td:contains(Modelo do Design))) tr:has(td.o_data_cell:contains(Evento em Livraria)) .o_priority",
        },
        {
            content: "e a coluna em que a subtarefa vai nascer",
            trigger: ".o_list_view th[data-name=stage_id]",
        },
        {
            // O endereço é o que fica: recarregar não pode abrir a lista
            // para os modelos de todos os projetos.
            content: "recarrega a página",
            trigger: ".o_list_view",
            run() {
                window.location.reload();
            },
            expectUnloadPage: true,
        },
        {
            content: "depois de recarregar, ainda só os modelos deste projeto",
            trigger: ".o_list_view:not(:has(td:contains(Modelo do Design))) td.o_data_cell:contains(Evento em Livraria)",
        },
    ],
});
