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
| **Direção** | a soma das outras funções, menos o Visitante (desde 10/08/2026 — ver §5) |

A regra dos boards financeiros não é uma trava escrita à mão — ela **cai
sozinha da matemática dos grupos**. O painel de orçamento exige os grupos do
`liber_budget` e os relatórios contábeis exigem `account_readonly` ou mais;
como só Direção e Financeiro/Gerente recebem esses grupos, só eles veem os
boards. Não há nada a manter.

> **Esta seção descreve a régua até 09/08/2026. A da Direção virou — ver §5.**
> Hoje a Direção é o **superconjunto da casa**: tudo que qualquer função
> alcança, ela alcança, inclusive os níveis de gerente. O parágrafo abaixo
> ficou como estava porque a régua que ele descreve segue valendo para todo
> mundo que não é diretor, e porque o caminho até a decisão nova começa nele.

Uma linha da tabela merece ser dita sem meia-palavra, porque a v1 a escrevia
errado. **A Direção opera.** Ela não é um perfil de consulta: os grupos que
carrega nos apps operacionais — vendas, consignação, contratos de direitos,
estoque, projetos — são de nível usuário, e com eles cria e edita documento
como qualquer operador. Isso é a decisão, não uma trava que ficou faltando:
quem dirige a casa mexe no que precisar mexer. A régua da Direção é para
cima, não para baixo — o que ela não recebe é o nível de **gerente** das
áreas (aprovar, configurar) e a configuração contábil, e diretor que também
gerencia uma área acumula a função dela. Em contabilidade o acesso é de
leitura; a exceção é o analítico, abaixo.

## 2.1. Contabilidade analítica

*Acrescentado em 02/08/2026.*

`analytic.group_analytic_accounting` passou a ser implicado por **Direção** e
**Financeiro/Gerente**. Antes não estava com ninguém — um grep pelo nome do
grupo em todo o repositório não achava nada —, e a consequência era concreta:
o menu `Faturamento ‣ Configuração ‣ Contabilidade analítica` (contas, planos
e modelos de distribuição) simplesmente não existia para usuário nenhum, e
`/odoo/analytic-accounts` respondia com erro de acesso, porque esse grupo é o
único ACL dos cinco modelos do `analytic`.

Duas coisas que essa linha ensina e que valem para a próxima:

- **O interruptor das Definições não estava ao nosso alcance.** O bloco
  "Análise" do formulário de configuração é `groups="account.group_account_user"`,
  e em base só-Faturamento (sem o `account_accountant`, que é Enterprise) o
  `group_account_manager` **não** implica `group_account_user` — a hierarquia
  está desenhada assim de propósito no `account_security.xml`. Ou seja: nem o
  administrador de Faturamento via a opção para marcá-la. Conceder o grupo
  pelo `implied_ids` contorna o formulário e é o lugar certo, já que é
  justamente o que este módulo existe para fazer.
- **Não há variante de leitura.** O `ir.model.access.csv` do `analytic` dá
  `1,1,1,1` nos cinco modelos para esse único grupo. Direção e Financeiro
  ganham criar/alterar/apagar conta e plano analítico; não dava para conceder
  menos sem escrever ACL própria.

Não precisou de script de migração. Na v19 a implicação virou fecho
transitivo **calculado** (`res.groups.all_implied_ids`, com
`res.users.all_group_ids` dependendo dele), então um `-u liber_roles` já
alcança todo mundo que hoje tem as duas funções.

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

> **Esta frase estava errada, e o erro custou dez dias — ver §5.** Tirar a
> linha do XML **não desfaz implicação nenhuma**: `implied_ids` com `(4, ...)`
> é comando incremental, então apagar a linha só deixa de mandar acrescentar a
> aresta. Ela sobreviveu a todo `-u` até 09/08/2026, quando entrou o
> `(3, ref('stock.group_stock_user'))` que de fato a corta. O parágrafo abaixo
> segue valendo para o outro caso, que é real: o grupo escrito **direto na
> ficha do usuário** pela propagação antiga, que nenhum XML alcança.

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

## 5. A revisão de 09/08/2026, e o que ela ensinou

*Acrescentado em 09/08/2026.* A matriz completa (14 perfis × 30 acessos) está
em `_mds/acessos-roles.md`, e os freios em `tests/test_acessos.py`.

O levantamento que originou esta seção foi feito de um jeito que vale repetir
na próxima vez: a matriz não foi lida do XML, foi lida do **fecho transitivo
real dos grupos no banco** (uma CTE recursiva sobre `res_groups_implied_rel`,
cruzada com os grupos de cada menu raiz). A diferença entre as duas leituras é
que era o problema — em dois casos o repositório dizia uma coisa e a base
fazia outra, e ninguém tinha como notar lendo só o código.

### O que mudou

1. **Marketing não era usuário interno.** Era o único departamento que não
   declarava `base.group_user`, e o único cujos grupos não o traziam de carona:
   `website.group_website_restricted_editor` é declarado no core sem
   `implied_ids` nenhum, ao contrário de `sale_salesman`, `stock_user`,
   `account_invoice` e `contract_user`. A ficha "Marketing", sozinha, não abria
   o backend — nem o app Site, que é gated em `base.group_user`. Nunca doeu
   porque a tela de Usuários concede o grupo por padrão: o buraco estava
   coberto por acidente, que é a pior forma de estar coberto.
2. **O Comercial ainda tinha o app Inventário.** Ver abaixo.
3. **O Financeiro/Gerente não via a contabilidade.** No v19
   `account.group_account_manager` implica **um** grupo, o
   `group_account_invoice` — a escada cheia mora no `account_accountant`, que é
   Enterprise. O gerente não via `Faturamento ‣ Contabilidade`, `‣ Análise` nem
   o painel do próprio app; via a Direção e via a conta pública de
   demonstração. Resolvido com `account.group_account_user`, que é o degrau que
   junta `basic` e `readonly` — o mesmo grupo que a §2.1 já tinha identificado
   como fora do alcance do formulário de Definições.
4. **Ninguém exportava.** `base.group_allow_export` só chegava por
   `base.group_system`. A régua nova é da direção: exporta quem gerencia — os
   seis Gerentes e a Direção, nenhum Assistente, e o visitante continua de fora
   pelo motivo de sempre.
5. **Ninguém editava o catálogo.** Era a pendência que esta seção substituiu.
6. **O cadastro de contato subiu para a gerência.** Comercial e Editorial
   cadastravam nos dois níveis e passaram a cadastrar só no Gerente; o
   Jurídico, que não cadastrava em nível nenhum, entrou no Gerente — o
   contrato de direitos costuma ser o primeiro documento da casa a citar um
   autor. O Financeiro ficou intacto nos dois níveis: a Cobrança precisa abrir
   o cliente para faturá-lo. Ver a ressalva logo abaixo, que é importante.
7. **A Direção virou o superconjunto da casa.** A régua de julho — opera mas
   não gerencia — não sobreviveu ao levantamento: a Direção não podia faturar,
   não podia editar a ficha de um livro, não podia gravar as transferências da
   consignação e via menos que a conta pública de demonstração. Nenhuma dessas
   ausências tinha sido decidida. A régua nova é "tudo que qualquer função
   alcança, a Direção alcança", inclusive configurar contabilidade e ajustar
   estoque, e está travada por um teste que se mantém sozinho: ele junta o
   fecho de todos os perfis e exige que não sobre nada fora do da Direção.

### A Direção deixou de ser uma lista (10/08/2026)

A régua de 09/08 estava certa; o **modo de escrevê-la**, não. O perfil
continuou sendo uma lista de dezoito grupos do Odoo, mantida à mão, e o teste
de superconjunto era um freio *depois do fato*: pegava o esquecimento na
próxima rodada de testes, não impedia o esquecimento. Duas pontes de fora
(`liber_support`, `liber_amazon_vendor`) tinham de escrever três linhas cada —
assistente, gerente **e Direção** — pelo mesmo motivo.

A virada é escrever a régua em vez de conferi-la. `group_direcao` passou a
citar **os seis Gerentes**, e só isso:

```xml
(4, ref('base.group_user')),
(4, ref('group_comercial_gerente')),   … os seis …
(4, ref('liber_copyright_contracts.group_contract_config')),
```

Consequências:

- Função nova, nível novo ou grupo novo em qualquer função entra na Direção
  **no mesmo `-u`**, sem ninguém lembrar. Ponte de fora só precisa da linha da
  função.
- `group_direcao` **desceu no arquivo**, para depois do Marketing/Gerente:
  `ref()` só resolve o que já foi carregado. É o mesmo tropeço já anotado em
  "o grupo novo sobe para antes de quem o cita".
- A única linha que continua escrita à mão é a exclusiva da Direção
  (`group_contract_config`), e por isso a lista de exclusivas é legível de um
  olhar.
- **O Visitante saiu da soma.** Ele não é uma função: é o único recorte
  restritivo do módulo, uma lista que *subtrai* (`(3, ...)` mais a faxina em
  Python). Somar uma subtração a um superconjunto não quer dizer nada. O que
  ele havia pegado em 09/08 — os grupos do Metabooks — chega hoje pelo
  Marketing/Gerente, e ganhou teste com nome próprio (§6b de
  `test_acessos.py`) para que a lacuna não volte sem freio.
- O teste de efeito continua lá, agora ao lado de um teste de **forma**, que
  exige os seis gerentes citados. Só o de efeito passaria também com a lista à
  mão de volta — verde no dia da mudança, vermelho meses depois.

Nada a migrar: `(4, ...)` nunca removeu aresta, então as dezoito antigas
seguem no banco e o fecho é o mesmo, só que daqui em diante ele cresce
sozinho.

### A ressalva do contato, que um grupo não pode prometer

A régua "cadastrar contato é de gerência" vale para o Editorial e para o
Jurídico, e **não vale para o Comercial** — não por descuido, mas porque o ACL
que concede o cadastro não é nosso. O addon `crm` do core dá read/write/CREATE
em `res.partner` a `sales_team.group_sale_salesman` (linha
`res.partner.crm.user`); é isso que faz funcionar cadastrar o cliente na hora,
de dentro da cotação. Fechar a porta exigiria tirar do Comercial o grupo de
vendas, ou seja, tirar dele a venda.

O que a saída do `partner_manager` deu de verdade ao assistente comercial: ele
perdeu o **unlink**. Cria contato, não apaga contato. O CSV do resumo tem duas
linhas separadas por causa disto — uma só mentiria por omissão. É a mesma
disciplina da §3: um grupo de segurança nunca deve prometer mais do que cumpre.

### A bonificação, e a seta que não se inverte

O superconjunto da Direção incluiu um grupo que este módulo **não pode citar**:
`capela_influencers.group_bonus_user`. O `liber_roles` largou aquela dependência
em 29/07 (módulo aberto não depende de proprietário), então quem liga os dois é
a ponte do outro lado, `_capela_ligar_no_visitante`. Ela passou a conceder à
Direção e ao visitante **na mesma chamada**, de propósito: assim as duas
concessões aparecem e somem juntas, e o teste de superconjunto nunca encontra
um estado pela metade — a ordem de carga entre módulos sem dependência é livre.

`base.group_partner_manager` também tinha entrado mais cedo em 09/08, antes da
virada: a Direção via a ficha de qualquer cliente e não conseguia cadastrar o
próximo.

### A lição que custou dez dias

**`implied_ids` escrito com `(4, ...)` é uma lista de comandos incrementais,
não uma declaração de estado.** Em 31/07 o `stock.group_stock_user` saiu da
lista do Comercial, e todo mundo — este arquivo inclusive, na §3 — leu isso
como "o Comercial não tem mais o app Inventário". Apagar a linha só deixa de
mandar acrescentar a aresta; não manda tirá-la. A aresta criada em julho
sobreviveu a todo `-u` desde então, e todo comercial cadastrado depois de 31/07
nasceu com o depósito na mão.

Três testes do `test_logistica.py` estavam **vermelhos** apontando exatamente
para isso. Não estavam sendo lidos. Vale mais que a correção em si: a suíte já
sabia, e a suíte é que traz o assunto à tona quando alguém a roda.

A correção é `(3, ref('stock.group_stock_user'))` no fim da lista — depois das
concessões, pelo mesmo motivo de ordem que o visitante ensinou em 27/07. E não
precisou de migração: no v19 `res.users.all_group_ids` é **calculado** a partir
de `group_ids.all_implied_ids` (é um `@api.depends`, não uma propagação
gravada), então cortar a aresta alcança todo mundo na hora. A migração
`19.0.1.1.0` segue valendo para o outro caso, que é o grupo escrito direto na
ficha do usuário pela propagação antiga.

### O catálogo, que era a pendência antiga desta seção

`product.group_product_manager` é o único grupo com `write` em
`product.template` (os demais ACLs do modelo são `1,0,0,0`), e não estava com
função nenhuma. O Editorial carregava o app Inventário inteiro justamente para
chegar ao livro e esbarrava no ACL de leitura: o app estava lá e a permissão
que ele foi buscar, não. O catálogo de uma editora era somente leitura para a
editora.

A decisão da direção é que o livro é de quem o faz, o vende e o divulga —
Editorial, Comercial e Marketing, no nível Assistente. Não precisou de menu
novo: `Metabooks ‣ Books` é uma ação sobre `product.template` sem trava de
grupo, e o Editorial e o Comercial ainda chegam pelo Inventário e por Vendas.

## 6. O que fica para depois

- **Compras não tem dono.** O app está instalado e nenhum perfil o alcança.
- **A Bonificação não tem administrador.** Desde 09/08 a Direção a vê (pela
  ponte do `capela_influencers`), mas `group_bonus_manager` — quem configura
  cotas, listas e scores — segue sem dono na grade. Comercial ou Marketing?
- **Dropbox, Drive e GitHub.** Três apps instalados que nenhum perfil alcança;
  nem a Direção, porque não é acesso que outro perfil tenha.
- **Os botões de envio à MVB.** `metabooks_product_group` trava dois botões da
  ficha do produto (*Metabooks* e *Refresh Technical Sheet*); a aba
  bibliográfica sempre foi aberta. Agora que o Editorial edita a ficha, a
  pergunta "quem edita deveria poder enviar?" ficou de pé.
- **A carona do site no Comercial/Gerente.** `sales_team.group_sale_manager`
  implica `website.group_website_restricted_editor` no core. A aresta não sai
  daqui, então desfazê-la pediria uma faxina em Python como a do visitante,
  para um risco que é de conteúdo e não de dado. Anotado no XML, não corrigido.
- "Assistente vê só os próprios documentos / só o seu canal" — é `ir.rule` por
  registro. Fácil de acrescentar por cima, difícil de acertar de primeira.
- Alçadas com valor (desconto acima de X% sobe para o gerente).
- O visitante não tem trava contra `sudo()`. Se algum dia isso importar, o
  caminho é auditar os botões, não endurecer o guarda.

---

## A reescrita de 11/08/2026: o módulo virou uma transcrição

O pedido foi este, e vale ser citado porque é a régua nova: *"me perdi sobre
os níveis de acesso. Queria propor um refazimento completo. Algo
extremamente mais simples: se escolho gerente_comercial, apenas mudo o campo
Vendas — é um mero atalho."*

O diagnóstico foi que **o atalho já existia na tela**; o que estava ilegível
era a tabela por trás dele. O formulário de usuário do Odoo 19 tem **25
opções**, cada uma uma escolha única, mais uma seção "Direitos extras" que só
aparece em modo debug — e das 60 caixinhas de lá, 45 são chaves globais dos
Ajustes, iguais para a casa inteira. Sobravam 6 decisões reais escondidas no
porão. Os papéis da casa **já são uma dessas 25 opções**.

O que mudou aqui:

1. **A decisão saiu do código.** Ela mora em `_mds/PERFIS.md`, que lista as 25
   opções e o que cada função marca em cada uma. Este módulo transcreve, e
   nada mais. Linha nova aqui sem linha lá é decisão sem dono.
2. **Cada função é uma lista chapada.** 762 → ~400 linhas. Nenhum `(3, ...)`
   fora do Visitante, nenhuma ordem que importe, nenhuma soma a decifrar.
3. **Retirada é migração, não linha apagada.** As quatro de 11/08 estão em
   `migrations/19.0.2.0.0/`, e fazem as duas metades — a aresta e a ficha de
   cada usuário. Apagar a linha do XML nunca fez nem a primeira.
4. **Módulo opcional traz a própria ponte.** A Bonificação passou a ser
   concedida pelo `capela_influencers`, como o Atendimento já era pelo
   `liber_support`.

### Três coisas que a execução corrigiu, e que valem mais que o resultado

- **O Editorial deixou de ser usuário interno.** Tirar o `stock.group_stock_user`
  cortou sem querer o único caminho dele até `base.group_user` — o mesmo
  buraco do Marketing em 09/08, pela mesma causa: o grupo chegava de carona.
  Os seis Assistentes passaram a declará-lo, e há um teste que varre as treze
  funções. **As duas vezes o buraco foi silencioso; agora não é mais.**
- **A regra de escrita em tarefa foi truncada na reescrita**, perdendo o ramo
  dos projetos com visibilidade "employees". Quem pegou foi
  `test_editorial_assistente_trabalha_a_tarefa`. É o argumento mais concreto
  que este módulo tem para manter a suíte cara que tem.
- **Os dois grupos caseiros de projeto quase foram aposentados** em nome de
  "usar o nativo". O `project.group_project_user` tem regra `0111`: cria e
  apaga tarefa em projeto alheio. O nativo não é o degrau que parece.

### O que deixou de ser dúvida (era §"o que ficou de fora")

- **Compras tem dono:** é o reino do Assistente financeiro.
- **A Bonificação tem administrador:** o Gerente de marketing.
- **Dropbox, Drive e GitHub** são do Editorial, nos dois níveis.
- **A carona do site no Comercial/Gerente** foi decidida, não corrigida:
  aceita-se. Cortá-la exigiria desfazer uma aresta do core para a casa toda.

### O que continua de pé

- O vazamento de `account.move` foi fechado no `liber_copyright_contracts_payments`,
  onde ele nascia — mas "só as faturas do meu **departamento**" continua sendo
  fase 2: exige um campo de departamento na nota e a árvore de funcionários,
  que ainda não existe (o prod tem 51 usuários internos e 1 ficha).
- O molde de novos usuários do Odoo traz *Produtos: Criar* ligado. Enquanto
  isso não for desmarcado nos Ajustes, "o Comercial não cria produtos" fura a
  cada pessoa cadastrada à mão.

---

## A régua do contato, e a tela que não abria (20/08/2026)

Três pedidos da direção, num só dia, e o terceiro é o que ensinou alguma coisa.

**1. O Jurídico/Gerente terminou de fazer o que já começava.** Ganhou
*Financeiro: Faturamento* e *Compras: Usuário*: a nota do autor é uma fatura
de fornecedor e o pedido que a origina é um pedido de compra, e até aqui quem
apurava o período tinha de pedir a outro departamento que digitasse o
documento que ele mesmo apurou. Ganhou também **Dropbox e Drive no nível
Gerente** — quem assina responde pela pasta onde o contrato assinado mora. O
GitHub ficou de fora: lá mora código. Nada disso desceu para o Assistente,
que segue redigindo minuta e mais nada.

**2. Cadastrar contato virou marca de nível, não concessão de departamento.**
Como já era a exportação: `base.group_partner_manager` nos seis Gerentes,
leitura em todos os Assistentes. Entraram a Logística (o endereço de coleta e
a transportadora nascem no depósito) e o Marketing (a lista de contatos é o
mailing). As duas exceções de baixo continuam, e por motivo: o assistente
financeiro cadastra porque a Cobrança abre o cliente para faturá-lo, e o
assistente comercial cadastra porque o ACL que concede é do `crm` e não é
nosso.

**A leitura não custou uma linha de XML** — o ACL do core já dá `res.partner`
em leitura a `base.group_user`, e toda função começa por ele. O que se
escreveu foi o teste.

### 3. E a leitura, que existia no ACL, não existia na tela

O pedido veio com um print anexado:

> Você não tem permissão para acessar registros de **'Contrato de
> Consignação'** (consignment.agreement).

Contato não tem nada com consignação. O que havia era um **cartão de
Consignação pendurado no formulário do parceiro** (`liber_soc_agreements`),
sem `groups`, cujo compute lê `consignment.agreement` **como o usuário**. O
formulário do contato é de todo mundo; o ACL da consignação não é. Resultado:
**dez das treze funções** — todas menos o Comercial, a Direção e o Visitante —
esbarravam no erro **antes de a tela desenhar**. A régua nova teria nascido
falsa por causa de um botão.

O conserto é do lado de lá, no `liber_soc_agreements`: `groups=` no campo (o
ORM tira do arch e nunca chama o compute) **e** no nó do botão (senão sobra um
botão cujo `invisible` cita um campo que não veio, e o cliente web trata
modificador com campo ausente como falso — botão visível e quebrado ao
clicar). `compute_sudo=True` seria a saída errada: faria o número aparecer
para quem não tem o app.

**O freio ficou genérico**, em `tests/test_contatos.py`: monta o formulário
como cada uma das treze funções, colhe todos os campos que o arch pede e lê um
a um. Qualquer módulo que amanhã pendure na ficha de contato um campo que lê
modelo cercado cai ali, e não no colo de quem for cadastrar uma livraria.

### A armadilha que quase deixou o teste verde com o bug em pé

Vale mais que o conserto, porque não é sobre este campo: **o cache do ORM é da
transação, não do usuário.** A primeira versão da varredura ia da Direção para
baixo e passava limpa. A Direção pode tudo, computava o campo, e todos os
perfis seguintes o encontravam no cache — nenhum deles chegava a chamar o
compute. Um `env.invalidate_all()` antes de cada leitura foi a diferença entre
"ninguém reclamou" e "está certo". Teste de acesso escrito sem isso mede o
primeiro usuário da lista, e mais nada.
