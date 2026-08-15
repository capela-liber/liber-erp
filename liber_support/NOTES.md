# liber_support — notas do protótipo

O desenho aprovado está em `_mds/atendimento-comercial.md`. Este arquivo
registra só o que o código fez **diferente** do desenho, e por quê.

## Desvios do desenho

1. **Horas de SLA moram na equipe, não em Configurações.** O calendário de
   trabalho já mora na equipe, e cada selo pode ter prazo próprio — separar
   as horas num `res.config.settings` global obrigaria a escolher um prazo
   só para as três caixas. Quatro campos no formulário da equipe.

2. **Reabertura velha não abre chamado novo.** A regra dos 7 dias virou:
   resposta em chamado fechado **sempre reabre**, e se o fechamento tem mais
   de 7 dias o chamado ganha uma nota interna sugerindo abrir um novo. O
   gateway de e-mail do Odoo casa a mensagem com a thread ANTES de chamar o
   modelo (`message_update`), e redirecionar a mensagem para um registro novo
   nesse ponto é briga contra o framework — não vale num protótipo.

3. **Família `liber_`, licença AGPL-3.** Nasceu `capela_support` em
   09/08/2026 e foi renomeado no dia seguinte, por decisão do usuário: o
   balcão de e-mail simples é do selo (`liber_`); `capela_` fica reservado
   ao atendimento multicanal complexo (Chatwoot, painéis, IA) do plano no
   worktree `worktree-capela-support`. Entrar no repositório público
   `liber-erp` é decisão separada, ainda não tomada.

4. **O visitante do `liber_roles` fica de fora por omissão.** Nenhum
   `ir.model.access` menciona os grupos dele, então o ORM já barra. Não há
   ponte — e é isso mesmo: atendimento é conversa de cliente, não vitrine.

## O que o protótipo não resolve (herdado do desenho)

- Captura das caixas por **encaminhamento** (como no Odoo 15): configurar o
  forward de `comercial@…` para o alias de cada equipe é trabalho de DNS/
  webmail, fora do módulo. O seed cria os aliases; o encaminhamento é manual.
- Migração dos chamados do Helpdesk do 15 — adiada de propósito.
- Relatório mensal (fase 2 do desenho) ficou de fora desta rodada; o kanban
  filtra por atraso e o cron cobra, mas não há visão agregada ainda.

## Rodar

Instalado **somente no `testing`**. Seed de encenação:

    docker exec -i edlab19-odoo odoo shell -d testing --no-http \
      < scripts/seed_support_testing.py

Testes (banco descartável próprio, todo o SOC junto por causa da ponte):

    docker exec edlab19-odoo odoo -d support_test \
      -i liber_support,liber_support_soc --test-enable \
      --stop-after-init --http-port=8079
