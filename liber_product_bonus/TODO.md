# `liber_product_bonus` — TODO

Inventário completo das features pensadas, com o que **já está de pé** assinalado.
Ler `NOTES.md` (o quê e por quê) e `UX.md` (como se usa). Correções dele em `LOG.md`.

**Estado: protótipo rodando no banco `bonus_demo`.** 37 testes verdes.
`[x]` = implementado e testado · `[ ]` = pensado, não feito · ⚠️ = decisão travando

```
Ver:   docker compose up -d  →  localhost:8069  →  banco bonus_demo  (admin/admin)
Testar: docker exec edlab19-odoo odoo -d bonus_demo -u liber_product_bonus \
          --test-enable --test-tags '/liber_product_bonus' --http-port=8072 --stop-after-init
Refazer o seed: docker exec -i edlab19-odoo odoo shell -d bonus_demo --no-http \
          < scripts/seed_bonus_demo.py     (idempotente)
```

---

## O núcleo — o disparo BO e a ficha B000

- [x] **`product.bonus.dispatch` — o disparador** (`BO/2026/00001`), que gera **uma ficha por
      pessoa**: cada uma tem endereço, pacote no depósito e nota própria (correção dele, 17/07)
- [x] `product.bonus` + `product.bonus.line` — a ficha (**`B00231`**), com chatter
- [x] Duas sequências: **BO/** para o disparo (duas letras = disparador, D4), **B00001** para a
      ficha (não é disparador → não leva as duas letras)
- [x] Aprovação **no disparo**: o responsável da lista diz sim uma vez, não 47
- [x] O disparo é a unidade que discute com mídia: "47 livros, R$ 580" vs "um anúncio, R$ 4.000"
- [x] `product.bonus.reason` — cadastro de motivos finos
- [x] Os **três baldes**: autor/editorial · marketing · comercial
- [x] Motivo roteia: balde, aprovação, janela de retorno
- [x] Escada `rascunho → aprovado → enviado → chegou → concluído`, + `não chegou` e `cancelado`
- [x] Autor **pula aprovação** (o contrato já aprovou na assinatura)
- [x] Grupos usuário/gestor (v19: `res.groups.privilege`)
- [x] Regra multi-empresa
- [x] Ícone, menus, `pt_BR.po` (62 strings: a escada, os baldes, os campos da tela)

## O freio — meta travada

- [x] **A porcentagem: `Bonificações > Configuração > Meta de doação (%)`** — 1,5% autor + 3%
      marketing + 0,5% comercial. Vale para todos os títulos, sem cadastrar nada.
      ⚠️ Ele perguntou **duas vezes** onde ficava: na primeira não existia; na segunda existia,
      renderizava, e estava no **Definições global** — onde a convenção do Odoo manda e onde
      ninguém dentro do app ia procurar. **Ajuste que nenhum usuário acha não existe**, então o
      caminho do menu virou teste de regressão
- [x] `product.bonus.quota` por título × balde é a **exceção**, e também por **%**
- [x] Reimpressão **alarga a meta sozinha** (a % é da tiragem, e a tiragem cresce)
- [x] ⚠️ **Sem tiragem em estoque → não trava**: meta de tiragem inexistente é *indefinida*, não
      zero. O lançamento sendo planejado hoje ainda não entrou no estoque, e bloqueá-lo falharia
      para o lado de "não mandou livro"
- [x] **Tiragem lida das ENTRADAS de estoque**, nunca do saldo (D1)
- [x] `% da tiragem` no produto e na meta
- [x] Bloqueio ao enviar acima da meta
- [x] Mensagem de bloqueio **explica**: permitido, doado, livre, e quem libera
- [x] Override de gestor (`bonus_force_quota`) **registrado no chatter**
- [x] **Contador vivo na triagem** — o freio aparece enquanto se escolhe (`UX.md` §2)
- [x] "Meta não gasta é pendência, não economia" na própria barra
- [ ] Meta **por lista** também (D10 = ambas) — hoje casa + título × balde

## A triagem — o coração (`UX.md` §4)

- [x] Tela cheia, não modal (U1)
- [x] **Quatro fontes que SOMAM** (não é rádio): **listas VIP** · **disparo anterior** ·
      **filtro** (etiqueta/UF) · **a dedo**. "A lista de imprensa mais os jornalistas de SP que
      não estão nela mais o Fulano que pediu" é um pedido normal, e o rádio o transformava em
      três disparos
- [x] **Disparo anterior como fonte** — o BO já é uma seleção curada; "manda para quem recebeu o
      livro anterior" é a base de mala direta mais natural, e torna quase desnecessário congelar
      campanha em lista
- [x] **Dedup entre fontes diferentes**: quem for achado por lista + BO + a dedo recebe um livro
- [x] **A aritmética na tela**: "24 nomes somados · 7 repetidos · 17 candidatos" — o dedup é
      trabalho invisível, e ver a conta é a diferença entre confiar na tela e contar na mão
- [x] Coluna **"de onde veio"** por pessoa — com 4 fontes, "por que fulano está aqui?" deixa de
      ser óbvio
- [x] ⚠️ **Filtro vazio adiciona ninguém** — antes caía em "todos os que recebem bonificação",
      o que com as fontes somando despejaria a agenda inteira em cima da lista
- [x] Uma linha por pessoa, com caixa de seleção
- [x] **As 5 colunas que são a decisão**: Já tem? · Recebeu · **Rendeu** · Último · Endereço
- [x] ⚠️ **Nunca bloqueia por volume** — Davi Reis, 22 livros, 0 de 22, e **segue selecionável**
- [x] Só a **duplicata** desmarca — visível (não há mais "não mandar mais": ver seção do retorno)
- [x] **Cold start**: quem não tem histórico é `—`, nunca `0`
- [x] `[Salvar seleção como lista]` — a curadoria boa vira lista
- [x] Conferência: prontas / sem endereço / duplicata / meta / estoque / custo
- [x] Gera **1 B000 por pessoa** (D7)
- [ ] Sugestão *"12 receberam o livro anterior e não receberam este"* (U5: fica p/ depois)

## O retorno — a outra metade da tese (`UX.md` §7)

- [x] Escala com **as palavras dele**: Silêncio · Meia-boca · Divulgou · Arrasou (U7)
- [x] **Janela por motivo** (U8) — Influencer 21 · Imprensa 120 · Comercial 60
      ⚠️ janela única faria o Estadão virar "silêncio"
- [x] **`aguardando` ≠ `silêncio`** — `deadline` + `is_waiting`, envelhece sozinho
- [x] Campo **link** da divulgação (U9) — sem link é opinião
- [x] **Taxa crua** `5 de 7` no parceiro e na lista — ⚠️ **nunca score 0–100** (U7/§7.5)
- [x] `não chegou` → **`[Reenviar]`**, e não conta contra o destinatário (§7.2)
- [x] Registro de um clique: lista *Rendeu?* com 4 botões por linha
- [x] **Sem "não mandar mais"**: decidir que um autor sai da lista para sempre é decisão
      editorial/de relacionamento, não escrituração de bonificação — não pertence a este módulo
      (retirado a pedido dele, 17/07). O histórico fica aqui para *informar* essa decisão; onde
      ela é registrada, se for, é outro lugar
- [ ] Atividade automática N dias após envio (U4) — **o sistema lembra, não a pessoa**
- [ ] Registro em lote ("estes 5 divulgaram")
- [x] **Análise (pivot / graph / lista)** cruzando **Investimento × Tipo de parceiro ×
      Resultado × Lista × Campanha × Título × Mês** — menu Bonificações > Análise
- [x] **Investimento** (o antigo "balde" renomeado — Autor/Editorial, Marketing, Comercial)
- [x] **Tipo de parceiro** (campo no contato: Autor/Jornalista/Influenciador/Livraria) — quem
      recebe, distinto de quem paga. Investimento vem do disparo; o relatório cruza os dois

## Listas VIP (`UX.md` §6)

- [x] `product.bonus.list` — dono (**aprova**), quem montou, quando, meta, gasto
- [x] `product.bonus.list.member` — **modelo, não m2m**: entrou_em, saiu_em, quem_adicionou
- [x] Sair da lista **preserva o histórico** (não apaga o membro)
- [x] Taxa de retorno por lista — diz qual lista vale a pena
- [x] Botão "Enviar bonificação" direto da lista
- [x] **Centenas de listas** (`UX.md` §6): o disparo aceita **várias listas** com dedup — quem
      está em duas recebe um livro só. É o caso comum, e não cria lista nenhuma
- [x] **Combinar em nova lista** — união / interseção / diferença, com a **sobreposição** no
      preview ("4 em mais de uma lista": diz se as listas são coisas diferentes ou a mesma com
      dois nomes)
- [x] **Proveniência**: a lista combinada lembra de quais veio e por qual modo
- [x] **Etiquetas** + busca + "nunca usadas" (acha o peso morto) + arquivar em vez de apagar
- [ ] ⚠️ **Importar membros** (CSV/planilha, **casar por e-mail**, prévia antes de gravar)
      — hoje só o import genérico do Odoo, que **duplica contato**. É o buraco mais feio
- [ ] ⚠️ **Etiquetas** — relatório QWeb em lote, folha conforme **U6**
      (⚠️ **pendente: que folha a casa usa?**). Sem isso ninguém posta 200 livros
- [ ] Fila "etiquetas a imprimir" que esvazia ao imprimir
- [ ] Higiene: membro sem bonificação há N meses → revisar

## Produtos

- [ ] Tiragem e % doado na ficha do produto (os campos existem, falta a view)

> **"Em Mãos" foi escondido e depois revertido** (17/07). Esconder `qty_available` fazia sentido
> pelo argumento — em casa de consignação ele mente, contando como "em mãos" o livro que está na
> prateleira da livraria — mas não pelo lugar: era um campo do **core**, escondido pelo módulo de
> **bonificação**, afetando o Odoo inteiro. Quem instalasse bonificação perderia o saldo em
> estoque sem nunca ter pedido isso. Se o incômodo voltar, o lugar é outro módulo, e a discussão
> é a da memória `soc-open-issues` ("Em mãos contando consignado").

## Histórico no contato

- [x] `bonus_count`, `bonus_last_date`, `bonus_lifetime_cost`, taxa de retorno
- [x] Botão-caixa + aba Bonificações na ficha do parceiro
- [x] Aviso de duplicata (coluna "Já tem?" na triagem)

## Acompanhamento

- [x] *A ligar* (era *A confirmar*) — `[Chegou] [Não]` + **telefone na linha**: a ação é LIGAR.
      **Gated por `days_to_call`** (Definições > Bonificações, provisório): só aparece quem foi
      expedido há X dias e não confirmou chegada. A data real de chegada (distância,
      transportadora) fica para depois
- [x] *Rendeu?* — `[Silêncio] [Meia-boca] [Divulgou] [Arrasou]` + link
- [x] **Ação em lote "Confirmar chegada"** (menu Ação da lista): marca várias como chegou de uma
      vez, depois de uma leva de ligações. Só as enviadas mudam
- [x] Título na lista de B000 e no acompanhamento; disparo com 1 ficha abre a ficha direto
      (o breadcrumb mostra o número B00xxx, não um "Bonus copies" genérico)
- [x] Filtros: aguardando, a confirmar, a avaliar, rendeu, silêncio, por balde
- [x] Agrupar por balde / motivo / retorno / lista / campanha / estado

## ⚠️ INV — o que este protótipo NÃO faz

**Deliberado, não esquecimento.**

- [x] **MOV** — `stock.picking` no tipo `BON/`, criado e validado no envio, sem backorder.
      **Específico**: nunca as Entregas do armazém. Não porque bonificação não seja faturada —
      no Brasil tudo tem XML, até jogar livro fora — mas porque a nota dela é **outra**: remessa
      (CFOP 5910), sem recebível, contra a nota de venda com recebível. Mesma movimentação
      física, documento fiscal diferente, e o tipo de operação é o que leva essa distinção até a
      emissão. Testado nos dois sentidos (é BON/ **e** não é o `out_type_id`)
- [x] **A ficha nunca reporta envio que não aconteceu** — `button_validate()` devolve wizard
      quando algo quer confirmação (era o `stock_sms`, que só dispara com telefone). Ignorar o
      retorno deixava o picking em `assigned` com a ficha dizendo `sent`. Agora recusa e explica
- [x] **A nota segue o padrão do repo**: `account.move` (tipo `entry`, CFOP 5910, **sem
      recebível** → sem pagamento) + `nfe.xml.panel` casado por chave. **Sem modelo próprio** —
      um `product.bonus.note` chegou a ser criado e foi **removido** (18/07): quebrava a simetria
      com C000/S000 e criava um terceiro lugar para procurar nota
- [x] **Todas as notas num lugar só**: Faturamento > NFe XML (a da bonificação aparece lá quando
      o XML é importado e casa pela chave)
- [ ] ⚠️ **Dívida do `liber_soc_fiscal_br`**: posições fiscais e CFOPs de consignação em Settings são
      **configuração morta** (declaradas, na tela, nunca lidas). Ver `NOTES.md`. Fora do escopo
      da bonificação — decidir depois se passam a ser consumidas
- [x] **Nota de simples remessa (CFOP 5910) mapeada**: "Gerar nota" exige o mapeamento fiscal
      (CFOP + contas em Definições > Bonificações); sem ele, erro citando o 5910
- [x] Faixas ("NOTA A EMITIR") removidas — o estado da nota fica no botão-caixa Lançamento/NF-e
      e na aba, não numa faixa
- [x] **Vínculo bidirecional** B000 ↔ lançamento: o `account.move` ganhou `bonus_id` (de volta
      para o B000, botão-caixa "Bonificação"). Antes só havia o `ref` em texto
- [x] **Config fiscal** em `res.company` + `Definições > Bonificações`: diário, conta de despesa,
      conta de saída de estoque, posição fiscal, CFOP — espelhando `liber_soc_fiscal_br`
- [x] **CFOP carimbado** na ficha (5910, `document_kind='bonus'` do `liber_nfe_xml`) para a emissão futura
- [ ] `cfop_id` em `account.move` propriamente (hoje o CFOP fica na ficha; o `account.move` é
      `entry`) — quando a emissão XML for real
- [x] **O B000 COORDENA logística + nota** (homólogo a C000/S000): não emite, amarra.
      Logística=`picking_id`, contábil=`entry_move_id` (o lançamento, a despesa), nota
      fiscal=`nfe_key`+`nfe_xml_panel_id` casada por chave (como o `account.move` do `liber_nfe_xml`)
- [x] **Estado fiscal**: a emitir → emitida → conciliada (`fiscal_state`), com botão Conciliar NF-e
- [x] Casamento com o XML por `nfe_key` (a NF-e emitida fora volta por importação e casa)
- [x] **Header no padrão C000/S000**: botões explícitos "Enviar para logística" (homólogo ao
      "Release to Logistics" do `consignment.move`) e "Confirmar nota", + **dois statusbars**
      (ciclo do documento + ciclo da nota: a emitir → emitida → conciliada)
- [ ] Visão unificada de todos os documentos num só lugar (ele pediu para NÃO fazer agora)
- [ ] Analítico: postar o custo no destino do balde (D2 = "tudo que entra e sai do livro
      e diz se deu lucro" → plano por título)
- [ ] ⚠️ Conferir contra `budget-analytic-plan-mismatch`: `budget_report` hardcodeia
      `account_id`; testar o relatório **de fato**

## Contratos — ponte `product_bonus_contracts`

Módulo à parte: marketing não deve depender de contratos para funcionar.

- [ ] `author_copies_qty` conforme **D5** (única decisão sem resposta; inclinação: na linha
      de royalty, porque contrato multi-obra quebra o campo no header)
- [ ] `author_copies_delivered` / `_remaining`
- [ ] **Um botão no contrato, não uma tela** (`UX.md` §3):
      `Exemplares 10 · entregues 4 · faltam 6 [Gerar B000]`
- [ ] Alerta quando entregue > devido — **avisa e deixa passar com registro**
- [ ] Se abater royalty: hook `_edlab_accrual_entry_domain()`

## T1 — bug vivo, independente deste módulo

- [ ] ⚠️ **`liber_nfe_xml` ignora o CFOP no import** (`grep -c cfop liber_nfe_xml/models/liber_nfe_xml.py` = **0**).
      Importar o painel de uma 5910 e apertar "Criar Fatura" gera `out_invoice` com **receita
      e recebível numa bonificação** — o que o `liber_soc_fiscal_br` proíbe no `sale.order` e
      ninguém proíbe no import. Merece PR próprio, não espera este módulo

## Testes

- [x] `tests/test_bonus.py` — **37 testes verdes**. Guardam o *desenho*, não só o código:
      sequência BO · custo congela · custo ≠ preço de capa · meta trava e **explica** ·
      override registrado · tiragem lê entradas e não saldo · autor pula aprovação ·
      aguardando ≠ silêncio · janela por motivo · perdido não pune + reenvia ·
      taxa crua nunca score · cold start é `—` · **triagem não bloqueia por volume** ·
      só duplicata desmarca · contador vivo · 1 B000 por pessoa · sem endereço fica fora ·
      `no_bonus` atribuído · membro preserva história
- [x] `scripts/seed_bonus_demo.py` — idempotente, 4 títulos, 18 pessoas, 2 listas,
      86 bonificações históricas com retorno, pipeline vivo
- [x] **Ações de navegação apontam para modelos que existem** — o buraco que o Odoo NÃO cobre.
      O core valida `<button name="X">` contra o modelo na instalação, então nome de botão morto
      já é pego. O que passa é o `res_model` **dentro do dicionário** que o método retorna: dado
      de tempo de execução, invisível a validador. Foi assim que `product.bonus.triage` viveu
      dois commits. Provado sabotando: com `res_model` morto o módulo instala **sem um erro**, e
      o teste fica vermelho
- [ ] Tour (`HttpCase`) da triagem ponta a ponta — precisa de Chrome real
- [ ] Atualizar `TESTING.md` com o módulo e o banco `bonus_demo`

## Decisões

**Respondidas por ele:** D1 (tiragem = estoque impresso até a campanha) · D2 (analítico do
livro = tudo que entra e sai, diz se deu lucro) · D3 (autor **não** cai em marketing) ·
D4 (**BO**) · D6 (aprova o responsável da lista) · D7 (1 por pessoa) · D8 (evento fora) ·
D9 (CFOP de simples remessa; falta a contabilidade) · D10 (metas: **ambas**) ·
U1–U5 OK'ados.

**Em aberto:**
- [ ] **D5** — entitlement no contrato ou na linha de royalty? (única sem resposta)
- [ ] **D9** — ⚠️ **como o INV existe sem recebível?** Trava o INV inteiro
- [ ] **U6** — ⚠️ **que folha de etiqueta a casa usa?** (o OK caiu na linha "perguntar a ele")
- [ ] **D1** — reimpressão: meta recalcula ou 2ª tiragem tem meta própria?

---

## Armadilhas que já custaram tempo (todas encontradas construindo isto)

- **`--` dentro de comentário XML** é ilegal. Custou dois ParseError.
- **v19: `_sql_constraints` saiu** → `models.Constraint('unique(...)', 'msg')`.
- **v19: `stock.move` não tem `name`.**
- **v19: `<group expand="0" string="...">` em search view** não passa no RelaxNG.
- **v19: `res.groups` sem `category_id`** → `res.groups.privilege`.
- **Campo `readonly=True` no modelo (ou na view) não volta do cliente.** Foi o pior:
  a triagem carregava 11 linhas **em branco**. As colunas de decisão têm de ser
  **computadas**, não escritas pelo onchange. Uma tela mostrando todo mundo como "0"
  é pior que nenhuma tela — parece uma resposta.
- **`_order` não aceita campo não-armazenado** (`Cannot convert ... to SQL`).
- **`self._fields['x'].selection` num campo `related` é um callable**, não uma lista —
  explodia justo dentro da mensagem de erro da meta, trocando a explicação por um traceback.
- **Seed com produto que tem movimento de estoque não se apaga** (FK). O catálogo é
  encontrado-ou-criado; a tiragem entra uma vez só.
- **Campo novo em modelo**: `--dev=reload` **não** cria coluna → `-u liber_product_bonus -d bonus_demo`.
- **`budget_report` hardcodeia `account_id`** — ver a seção do analítico.

## Nota de remessa (18/07 — desenho fechado)
- [x] Módulo `liber_nfe_remessa`: diário REM/, auto-paid da posição fiscal (campos homônimos do O15), baixa automática conciliada, menu Faturamento > Remessas, Faturas só com venda
- [x] B000 gera nota REM/ (out_invoice) — morreu o entry; Settings enxuto (posição fiscal + CFOP)
- [x] COM/ para a logística da consignação (REM/ liberado para o documento fiscal); consig_demo/testing migrados
- [x] C000 gera nota REM/ com a posição fiscal de consignação (o campo da posição de remessa ganhou consumidor; CFOPs ainda sem)
- [x] Remessas separáveis por origem (remessa_origin plugável + filtros); [ ] atalhos de menu dentro dos apps Consignação/Bonificações
- [ ] Módulo de eventos (futuro): nova posição fiscal no mesmo diário, zero código

## Nota do parceiro (18/07)
- [x] Nota com recência + encolhimento + "em teste"; direção (↑ → ↓); tudo em Definições
- [x] Coluna na seleção do BO, nos membros das Listas e painel auditável na ficha do contato
- [x] Relatório cruza pela situação CONGELADA no envio (não a de hoje)
- [ ] Nota por gênero/coleção (um influencer ótimo em poesia pode ser silêncio em ensaio)
- [ ] O hábito de registrar: sem isso todo mundo vira "em teste" e a tela fica muda

## Importação (18/07)
- [x] Importar planilha (.xlsx/.csv) criando a lista junto; prévia; casamento por e-mail e nome; sinônimos de cabeçalho; modelo .xlsx gerado pelo próprio código
- [ ] Importar também para "Contatos com etiqueta" (hoje o import só alimenta listas)
- [ ] Relatório linha a linha do que foi ignorado (hoje só o total agregado)
