# Módulo `liber_roles` — notas de concepção

> Perfis de acesso por **função da casa**, e a conta **visitante** da
> apresentação pública.
> Desenho de 2026-07-15, implementado em 2026-07-20.
>
> **Ressalva honesta, e ela vale a leitura:** os perfis por departamento
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

Departamento × nível, mais a Direção. Os departamentos são **Comercial,
Logística, Financeiro, Editorial e Marketing**:

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

## 3. Logística, e o preço de separá-la do Comercial

*Acrescentado em 31/07/2026.*

A grade de julho tinha quatro departamentos e um buraco: **ninguém do
depósito**. Quem trabalha na expedição não tinha função, e as duas saídas eram
igualmente ruins — receber a ficha do Comercial (e com ela os pedidos, os
clientes e os acertos, que não são dele) ou receber o grupo nativo do Odoo na
mão, que é exatamente a tradução manual que este módulo existe para eliminar.

A função nova é literal: **o app Inventário, e só ele.** As transferências da
consignação (`COM/`, `RET/`, `ACERTO/`) aparecem lá dentro como qualquer
outra, que é como o depósito precisa vê-las: uma fila de coisas a separar e
despachar. O *documento* da consignação — o acordo, a campanha, o acerto —
fica de fora.

### O que custou: o Comercial estava com o depósito na mão

O Comercial carregava `stock.group_stock_user`, e com ele o app Inventário
inteiro: contagem de inventário, cadastro de armazém e localização, tipos de
operação, sucata, reposição. Criar a Logística sem mexer nisso teria criado
uma função, não uma separação.

E tirar o grupo, simplesmente, **quebraria a consignação**. O motivo está no
código e é bom lê-lo antes de mexer aqui: os pickings da consignação são
gravados **como o usuário**, não como superusuário —

- `liber_soc_moves/models/consignment_move.py` → `_create_picking()`: confirmar
  e soltar uma remessa cria o `COM/`;
- `liber_soc_settlement/models/consignment_settlement.py` →
  `_create_shelf_outflow()`: o acerto cria **e valida** o `ACERTO/`.

Um comercial sem direito de escrita em `stock.picking` levaria um `AccessError`
no meio de uma campanha.

Daí o desenho: um grupo estreito, **`liber_soc_moves.group_consignment_stock_docs`**,
declarado no módulo que precisa dele, dando exatamente dois modelos
(`stock.picking` e `stock.move`) e nenhum menu. O Comercial troca o app pelo
grupo; a Logística fica com o app.

E a parte que este grupo **não** entrega, dita em voz alta porque um grupo de
segurança nunca deve prometer mais do que cumpre: isso é uma separação de
**apps**, não de registros. Quem tem o grupo pode escrever qualquer picking
pelo ORM, inclusive uma entrega de armazém — não existe regra de registro no
Odoo que recorte pickings por tipo de operação. O que saiu do Comercial foi o
app Inventário, o ajuste de estoque e a configuração do depósito.

### A limpeza das fichas já cadastradas

Tirar um grupo de `implied_ids` desfaz a implicação e **não** tira o grupo de
quem já o tem — a mesma armadilha que já mordeu o visitante (seção 4). Por
isso a mudança vem com `migrations/19.0.1.1.0/post-comercial_sem_inventario.py`,
que retira o `stock.group_stock_user` dos comerciais já cadastrados — e só de
quem não tem outra função que o conceda, pergunta feita ao fecho transitivo
(`all_implied_ids`), não a uma lista para manter à mão.

## 4. O visitante

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

## 5. O que fica para depois

- **Editorial ainda carrega o app Inventário** (`stock.group_stock_user`), pelo
  mesmo motivo histórico que o Comercial carregava: é por ali que se chega à
  ficha do livro. Só que o Editorial **não edita** ficha nenhuma hoje — escrever
  em `product.template` pede `product.group_product_manager`, que nenhuma função
  concede. Ou seja: o app está lá e a permissão que ele foi buscar, não. Merece
  a mesma cirurgia que o Comercial levou em 31/07, e não foi feita junto porque
  arrumá-la é decidir o que o Editorial pode gravar no catálogo — outra
  conversa.
- "Assistente vê só os próprios documentos / só o seu canal" — é `ir.rule` por
  registro. Fácil de acrescentar por cima, difícil de acertar de primeira.
- Alçadas com valor (desconto acima de X% sobe para o gerente).
- Direção enxerga tudo em leitura, mas ainda **não está impedida** de editar
  nos apps operacionais. Diretor que opera uma área acumula a função dela.
- O visitante não tem trava contra `sudo()`. Se algum dia isso importar, o
  caminho é auditar os botões, não endurecer o guarda.
