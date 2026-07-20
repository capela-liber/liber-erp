# Módulo `liber_roles` — notas de concepção

> Perfis de acesso por **função da casa**, e a conta **visitante** da
> apresentação pública.
> Desenho de 2026-07-15, implementado em 2026-07-20.
>
> **Ressalva honesta, e ela vale a leitura:** os nove perfis por departamento
> rodam numa base real, mas foram **pouco exercitados** — a régua "Assistente
> opera / Gerente aprova" é uma primeira aproximação e vai apertar em alguns
> lugares e vazar em outros. O `visitante` é o que tem teste automatizado
> (`tests/test_visitante.py`). Trate o resto como ponto de partida, não como
> gabarito.

---

## 1. Motivação

Os perfis nativos do Odoo são recortes por **aplicativo**: "Vendas: Usuário",
"Contabilidade: Contador", "Estoque: Administrador". Uma editora não pensa
assim. Ela pensa por **função**: Comercial, Financeiro, Editorial, Marketing —
cada um em dois níveis — mais a Direção, que é transversal.

Traduzir uma coisa na outra é um trabalho chato, e ele costuma acontecer no
pior lugar possível: na tela de usuários, à mão, por quem clicou por último.
O resultado é que ninguém sabe responder "quem pode ver a margem?" sem abrir o
Odoo e conferir usuário por usuário.

Este módulo move essa tradução para o repositório, onde uma decisão de acesso
pode ser lida, revisada e versionada. O operador marca **uma** função na ficha
do usuário; o Odoo deriva o resto via `implied_ids`.

## 2. A grade

Departamento × nível, mais a Direção:

| Função | Régua |
|---|---|
| **Assistente** | opera o dia a dia: cria e edita os documentos da sua área |
| **Gerente** | tudo do assistente, mais aprovar e configurar |
| **Direção** | leitura ampla e os boards financeiros; transversal |

A regra dos boards financeiros não é uma trava escrita à mão — ela **cai
sozinha da matemática dos grupos**. O painel de orçamento exige os grupos do
`liber_budget` e os relatórios contábeis exigem `account_readonly` ou mais;
como só Direção e Financeiro/Gerente recebem esses grupos, só eles veem os
boards. Não há nada a manter.

## 3. O visitante

Fora da grade existe uma décima função que não é uma função da casa: a conta
da **apresentação pública**. Ela enxerga o sistema inteiro — pedidos,
consignação, contratos, orçamento, relatórios — e escreve no chatter, mas não
cria, altera nem apaga documento algum. Não emite um pedido; manda um recado.

### Por que não bastam "grupos de leitura"

Porque os grupos do Odoo **somam permissão e nunca subtraem**. Não existe
grupo capaz de cancelar o `write` que outro grupo concedeu. Montar um visitante
só com grupos significaria escolher, para cada app, um grupo que já fosse
somente-leitura — e na maioria dos apps esse grupo não existe.

### Onde a trava mora

Em `ir.model.access.check` (`models/ir_model_access.py`), por onde passa todo
`create/write/unlink` do ORM. Cortar ali, e não no menu, fecha junto a chamada
por RPC e a URL colada no navegador — que é o que interessa numa conta que vai
circular em público.

Como a escrita já está travada no ORM, os **grupos** do visitante podem ser
generosos: ele recebe nível gerente na maioria dos apps. Isso não lhe dá poder
nenhum a mais; dá **visibilidade**. É a diferença entre demonstrar o sistema e
demonstrar um sistema com metade dos menus faltando.

O que ele pode gravar é uma **allowlist** curta — chatter, seguidores,
atividades, anexos, preferências da própria sessão. Allowlist e não lista
negra: lista negra vaza, porque todo modelo novo nasceria gravável.

### O chatter

Para o Odoo, comentar num documento é um ato de escrita: o `mail.message` só
nasce se o autor tiver `write` no documento (`_mail_post_access`). Modelos
voltados ao portal baixam isso para `read` — é assim que um cliente comenta
numa tarefa que não pode editar. O visitante quer esse mesmo regime em todo o
sistema, e `models/mail_thread.py` o concede: quem pode ler, pode comentar.

### Duas fronteiras, ditas em voz alta

- **`sudo()` passa.** Código que grava como superusuário não é interceptado —
  é o preço de não quebrar login, cron e envio de e-mail. Os botões comuns do
  Odoo (confirmar pedido, validar fatura) gravam como o usuário e ficam
  barrados; um módulo que faça `record.sudo().write(...)` num botão, não.
- **Assistentes abrem.** Modelos transitórios são graváveis, então o
  assistente abre e preenche; o efeito dele cai no modelo real, que segue
  bloqueado. Numa demonstração é melhor falhar no "Aplicar" do que ter um menu
  que nem abre.

### Duas ausências deliberadas

- `account_manager`: leitura já basta para os relatórios contábeis; o nível
  gerente só acrescentaria telas de configuração.
- `base.group_allow_export`: a conta é pública e circula. Sem escrita, ela
  ainda poderia levar a base embora num `.xlsx`.

## 4. O que fica para depois

- "Assistente vê só os próprios documentos / só o seu canal" — é `ir.rule` por
  registro. Fácil de acrescentar por cima, difícil de acertar de primeira.
- Alçadas com valor (desconto acima de X% sobe para o gerente).
- Direção enxerga tudo em leitura, mas ainda **não está impedida** de editar
  nos apps operacionais. Diretor que opera uma área acumula a função dela.
- O visitante não tem trava contra `sudo()`. Se algum dia isso importar, o
  caminho é auditar os botões, não endurecer o guarda.
