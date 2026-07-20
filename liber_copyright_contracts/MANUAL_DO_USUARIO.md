# Manual do Usuário — Contratos de Direitos Autorais (Copyright Contracts)

Gestão de contratos de direitos autorais para uma editora: vincula
beneficiários (autores, tradutores, ilustradores) a obras (produtos), registra
o percentual de royalties por faixa de tiragem, apura os royalties a partir das
vendas, paga os autores por meio de contas a pagar, retém o IRRF e emite a
prestação de contas para cada autor.

> **Versão:** 19.0 · **Autor:** EdLab Press · **Licença:** LGPL-3

---

## Índice

1. [Visão geral e arquitetura](#1-visão-geral-e-arquitetura)
2. [Instalação](#2-instalação)
3. [Permissões e grupos de segurança](#3-permissões-e-grupos-de-segurança)
4. [Configuração inicial](#4-configuração-inicial)
5. [Cadastro de contratos](#5-cadastro-de-contratos)
6. [Linhas de royalties e faixas de tiragem](#6-linhas-de-royalties-e-faixas-de-tiragem)
7. [Contas analíticas dos beneficiários](#7-contas-analíticas-dos-beneficiários)
8. [Apuração de royalties a partir das vendas](#8-apuração-de-royalties-a-partir-das-vendas)
9. [Relatório de dívidas de royalties](#9-relatório-de-dívidas-de-royalties)
10. [Pagamento dos autores](#10-pagamento-dos-autores)
11. [Retenção de IRRF](#11-retenção-de-irrf)
12. [Prestação de contas ao autor](#12-prestação-de-contas-ao-autor)
13. [Automações (tarefas agendadas)](#13-automações-tarefas-agendadas)
14. [Fluxo completo — passo a passo](#14-fluxo-completo--passo-a-passo)
15. [Glossário](#15-glossário)

---

## 1. Visão geral e arquitetura

O produto é composto por **cinco módulos encadeados**. Você instala apenas o que
precisa: cada camada adiciona funcionalidades sobre a anterior. Instalar a
última traz todas as demais como dependência.

| Módulo | O que adiciona | Depende de |
|--------|----------------|------------|
| **Copyright Contracts** (`liber_copyright_contracts`) | Contratos, beneficiários, obras e faixas de royalties. Registra apenas os *termos* do contrato. | base, mail, contacts, product |
| **Analytics** (`liber_copyright_contracts_analytics`) | Conta analítica por linha de royalty, apuração dos royalties a partir das vendas pagas e relatório de dívidas. | Copyright Contracts, analytic, account, sales_team |
| **Payments** (`liber_copyright_contracts_payments`) | Gera contas a pagar (vendor bills) para pagar os autores a partir dos royalties em aberto. | Analytics, account |
| **Author Reports** (`liber_copyright_contracts_reports`) | Página do autor no contato e a *Prestação de contas* (PDF + e-mail). | Payments |
| **Taxes / IRRF** (`liber_copyright_contracts_taxes`) | Retenção do IRRF sobre o pagamento aos autores e acúmulo do imposto numa conta ao governo. | Author Reports |

**Ordem de dependência:** `liber_copyright_contracts` → `analytics` → `payments` →
`reports` → `taxes`.

Todos os menus ficam sob o aplicativo **Copyright** no menu principal do Odoo.

### Estrutura de menus

```
Copyright
├── Contracts            → contratos de direitos autorais
├── Beneficiaries        → contatos que são beneficiários (autores)
├── Analytic Accounts    → contas analíticas dos royalties
├── Reports
│   └── Royalty Debts    → relatório (pivô/lista) das dívidas de royalties
├── Bills
│   ├── To Pay           → contas de royalties a pagar
│   └── Paid             → contas de royalties já pagas
└── Settings
    ├── Preferences      → configurações gerais
    └── IRRF Tables      → tabelas progressivas do IRRF
```

> Algumas entradas (Analytic Accounts, Reports, Bills, IRRF Tables, Beneficiaries)
> só aparecem depois que a respectiva camada estiver instalada.

---

## 2. Instalação

1. Copie a pasta dos módulos para o diretório de *addons* do Odoo.
2. Em **Configurações › Ativar o modo de desenvolvedor**, atualize a lista de
   aplicativos (**Aplicativos › Atualizar Lista de Aplicativos**).
3. Instale o módulo desejado. Para o conjunto completo, instale
   **Copyright Contracts - Taxes (IRRF)** — ele traz as quatro camadas anteriores
   automaticamente.
4. Os módulos base e as camadas *Taxes* e *Reports* trazem **dados de
   demonstração** (contratos, obras e tabela IRRF de exemplo) quando o banco é
   criado com demo ativado.

---

## 3. Permissões e grupos de segurança

O módulo define dois grupos, sob a categoria **Copyright**:

| Grupo | Pode fazer | Não pode |
|-------|-----------|----------|
| **User** | Ver e editar contratos, linhas de royalties, gerar contas analíticas, apurar royalties e emitir prestações de contas. | Alterar a **data do último pagamento** de uma linha de royalty. |
| **Administrator** | Tudo do usuário **mais** definir/alterar manualmente a **data do último pagamento** (marco que "fecha" um período pago). | — |

Atribua o grupo em **Configurações › Usuários e Empresas › Usuários**, aba
*Permissões de acesso*, campo **Copyright**.

> A data do último pagamento também é atualizada **automaticamente** quando uma
> conta de royalty é paga (camada *Payments*); a restrição acima vale apenas para
> a edição manual.

---

## 4. Configuração inicial

Cada camada acrescenta seus próprios parâmetros. Configure-os antes de operar.

### 4.1 Preferência geral (módulo base)

**Copyright › Settings › Preferences** (ou **Configurações › Copyright**):

- **Contract expiry reminder (days)** — quantos dias antes do vencimento a rotina
  diária cria uma atividade de lembrete para o responsável pelo contrato.
  Padrão: **45 dias**. É um valor único para todo o banco.

### 4.2 Analytics — apuração e contas contábeis

Em **Configurações › Empresas** (ou nas preferências), aba/ seção *Copyrights*:

- **Analytic Plan** — plano analítico onde as contas dos beneficiários serão
  criadas.
- **Expense Account** — conta de despesa que espelha os royalties recém-apurados.
- **Liability Account** — conta de passivo para onde os royalties **vencidos**
  migram.
- **Liability After (months)** — a partir de quantos meses de atraso um royalty
  deixa de figurar na despesa e passa ao passivo.
- **Special Sales Teams** — equipes de venda consideradas "vendas especiais".
- **Special Sales Min. Discount (%)** — desconto mínimo que qualifica uma venda
  como especial (royalty calculado sobre o valor líquido faturado).

### 4.3 Payments — geração das contas a pagar

- **Payment Product** — produto usado nas linhas da conta a pagar do autor.
- **Payment Account** — conta de despesa dessas linhas.
- **Payment Journal** — diário de compras onde as contas são lançadas.
- **Due in (days)** — prazo (em dias) para o vencimento da conta a pagar.

### 4.4 Taxes / IRRF

- **Tax Authority** — contato (governo) destinatário da conta de imposto acumulada.
- **IRRF Liability Account** — conta de passivo "IRRF a recolher".
- **Tax Bill Journal** — diário da conta de imposto.
- **Tax Due Day** — dia do mês seguinte em que o imposto acumulado vence.

Além disso, mantenha a **tabela do IRRF** em
**Copyright › Settings › IRRF Tables** (ver [seção 11](#11-retenção-de-irrf)).

---

## 5. Cadastro de contratos

Acesse **Copyright › Contracts** e clique em **Novo**.

### Campos principais

| Campo | Descrição |
|-------|-----------|
| **Number** | Numeração automática (sequência `edlab.contract`). Preenchida como *New* até salvar. |
| **Signature Date** | Data de assinatura. |
| **Expiration Date** | Data de vencimento. |
| **Responsible** | Usuário responsável por acompanhar o contrato (recebe os lembretes). |
| **Company / Currency** | Empresa e moeda (moeda deriva da empresa). |
| **Tags** | Etiquetas coloridas para classificar contratos. |
| **Location** | URL ou local de arquivamento do contrato físico/digital. |
| **Auto-Renewable** | Se marcado, a rotina diária renova o contrato ao vencer. |
| **Renewal Term (years)** | Prazo (anos) somado ao vencimento a cada renovação. Sugerido a partir do intervalo assinatura→vencimento, mas fica fixo depois. |
| **Time Left / Days to Expiration** | Exibição do tempo restante (calculado). |

### Ciclo de vida (status)

```
Draft ──validar──▶ Valid ──renovar──▶ Renewed
   │                 │                    │
   └────cancelar─────┴──── Cancelled      └── (vencimento) ─▶ Expired
```

- **Validate** — coloca o contrato em *Valid*.
- **Renew** — estende o vencimento pelo *Renewal Term* e marca como *Renewed*
  (registra a data no chatter).
- **Cancel** — marca como *Cancelled*.
- **Expired** — atribuído automaticamente pela rotina diária quando o contrato
  vence e não é auto-renovável.

### Reatribuir responsável (em lote)

Na **lista de contratos**, selecione vários registros e use **Ação › Reassign
Responsible**. Escolha o novo responsável e confirme — todos passam a apontar
para ele.

### Campos derivados úteis

- **Beneficiaries** e **Works** — listas calculadas a partir das linhas de
  royalties (quem participa e quais obras o contrato cobre).
- Nos contatos e produtos, um botão inteligente **Copyright Contracts** mostra
  os contratos em que aquele contato é beneficiário ou aquele produto é obra.

---

## 6. Linhas de royalties e faixas de tiragem

Dentro do contrato, na aba **Royalties**, cada linha representa a combinação
**beneficiário × obra**.

| Campo | Descrição |
|-------|-----------|
| **Beneficiary** | O autor/tradutor/ilustrador que recebe. |
| **Work** | O produto (obra) sobre o qual incide o royalty. |
| **Recoupable Advance** | Adiantamento já pago, **recuperável** contra os royalties que a obra gerar. |
| **Non-Recoupable Advance** | Adiantamento não recuperável. |
| **Tiers** | Faixas de tiragem com o percentual aplicável. |

> Não é possível repetir a mesma combinação *contrato + beneficiário + obra* —
> há uma restrição de unicidade.

### Faixas (Tiers)

Cada faixa define **From (copies)**, **To (copies)** e **Percentage (%)**:

- **De / Até** delimitam a tiragem acumulada; **Até = 0** significa "sem limite
  superior".
- O percentual é escolhido pela faixa em que cai a **quantidade acumulada**
  vendida da obra. Se a quantidade ficar abaixo da primeira faixa, usa-se a
  última faixa como fallback.
- A data final deve ser ≥ à inicial (validação automática).

**Exemplo:**

| De | Até | % |
|----|-----|---|
| 0 | 3000 | 8,00 |
| 3001 | 10000 | 10,00 |
| 10001 | 0 (sem limite) | 12,00 |

---

## 7. Contas analíticas dos beneficiários

> Disponível a partir da camada **Analytics**.

Cada linha de royalty precisa de uma **conta analítica** para acumular o que é
devido/pago. O nome é montado a partir do número do contrato, referência interna
do produto, produto e beneficiário.

### Criar as contas

- **No contrato:** botão **Create Analytic Accounts** — abre um assistente
  listando todos os beneficiários; marque quais criar/sincronizar e confirme.
  Também funciona em lote a partir do menu *Ação* na lista de contratos.
- **Na linha:** ação **Create Analytic Account** — cria (ou apenas sincroniza o
  nome) da conta daquela linha.

### Adiantamento recuperável

Ao criar/atualizar a conta, o **Recoupable Advance** é lançado como um valor
**positivo** de abertura na conta analítica, datado na assinatura do contrato.
Isso faz com que os royalties que forem se acumulando **recuperem primeiro** o
adiantamento antes de gerar saldo a pagar. O lançamento é idempotente: um por
linha, atualizado quando o adiantamento muda e removido quando é zerado.

Ver as contas em **Copyright › Analytic Accounts**.

---

## 8. Apuração de royalties a partir das vendas

> Disponível a partir da camada **Analytics**.

Os royalties são apurados a partir das **faturas de cliente pagas** (ou
em pagamento / estornadas) que vendem as obras dos contratos.

### Como apurar

- **No contrato:** botão **Fill Royalty Lines** — varre todas as faturas de
  cliente pagas das obras do contrato e lança, em cada conta analítica, o royalty
  devido. É **idempotente** (não lança o mesmo royalty duas vezes — cada linha
  analítica guarda a fatura de origem).
- **Nas faturas:** selecione faturas de cliente e use a ação **Generate Royalty
  Analytic Lines** para apurar apenas as selecionadas.

Cada linha de royalty apurada guarda o **percentual aplicado** (da faixa da
quantidade acumulada) e a **fatura de origem**.

### Vendas especiais

Vendas feitas por uma **equipe especial** (configurada na empresa) com desconto
igual ou superior ao mínimo definido são tratadas como **vendas especiais**: o
royalty é calculado sobre o **valor líquido faturado**. No contrato, o botão
inteligente **Special Sales** abre a lista dessas faturas.

### Saldo em aberto

O contrato mostra **Open Royalties** — a soma dos saldos analíticos dos
beneficiários (royalties ainda devidos). Períodos já pagos são "quitados" pelos
lançamentos de corte e deixam de contar.

---

## 9. Relatório de dívidas de royalties

> Disponível a partir da camada **Analytics**.

**Copyright › Reports › Royalty Debts** apresenta os lançamentos analíticos de
royalties em duas visões:

- **Pivô** — por conta financeira × beneficiário nas linhas, ano nas colunas,
  medindo **Charged** (apurado/devido), **Paid** (pago) e **Balance** (saldo).
- **Lista** — data, conta analítica, beneficiário, conta financeira, % de royalty,
  quantidade, cobrado, pago e saldo (somados).

Filtros disponíveis: *Charged (owed)*, *Paid (payments)*, *Accrued (royalties)*,
*Payments/Cutoffs*, e agrupamentos por conta financeira, beneficiário, obra etc.

> **Charged** = lado negativo (royalty devido). **Paid** = lado positivo
> (pagamentos/quitações). **Balance** = soma dos dois.

---

## 10. Pagamento dos autores

> Disponível a partir da camada **Payments**.

Transforma os royalties em aberto em **contas a pagar (vendor bills)**.

### Gerar as contas

No contrato (ou em lote pela lista), clique em **Generate Royalty Bills**:

- Cria **uma conta por beneficiário**, com **uma linha por obra** que ainda deve
  royalties e ainda **não tem uma conta em aberto**.
- Cada linha carrega o **produto da obra** e sua **conta analítica**.
- Cabeçalho: data de hoje, vencimento em *Due in (days)*, referência com o número
  do contrato e o beneficiário (`contrato · beneficiário`).
- É preciso ter o **Payment Product** configurado na empresa; caso contrário o
  sistema alerta.
- Se não houver nada a pagar, uma notificação informa que os beneficiários não
  têm royalties em aberto ou já possuem contas.

### Acompanhar

- **Copyright › Bills › To Pay** — contas de royalties ainda não pagas.
- **Copyright › Bills › Paid** — contas já pagas.
- No contrato, botões inteligentes abrem as contas do contrato (todas, a pagar,
  pagas).

### Baixa do pagamento

Quando a conta é **paga**, a **data do último pagamento** da linha de royalty é
atualizada automaticamente — isso permite que a camada analítica "feche" o
período correspondente (lançamento de corte que quita o que foi apurado até ali).

---

## 11. Retenção de IRRF

> Disponível a partir da camada **Taxes / IRRF**.

Calcula o IRRF retido de cada conta de pagamento ao autor seguindo o método do
contador: **tabela progressiva + redutor (Lei 15.270/2025) + desconto
simplificado**, sem retenção até o limite de isenção configurado.

### Tabela do IRRF (configurável)

Em **Copyright › Settings › IRRF Tables**, mantenha a tabela vigente:

| Campo | Descrição |
|-------|-----------|
| **Name** | Nome da tabela (ex.: *IRRF 2026*). |
| **Validity (date_from)** | A partir de quando a tabela vale. |
| **No withholding limit** | Renda até a qual não há retenção. |
| **Simplified discount** | Desconto simplificado. |
| **Reducer (a / b / cap limit)** | Parâmetros do redutor da Lei 15.270/2025. |
| **Progressive Brackets** | Faixas com *amount to*, *rate (%)* e *deductible*. |

A tabela é escolhida pela data e mantida pelo contador quando a lei muda.

### Como funciona a retenção

Ao **confirmar (postar)** a conta de pagamento do autor, se houver IRRF a reter:

1. O imposto é lançado como uma **linha negativa** na conta do autor (o valor a
   pagar passa a ser o **líquido**), contra a conta de passivo **IRRF a recolher**.
2. O imposto é **acumulado** numa única conta a pagar (rascunho) endereçada ao
   **contato do governo**: uma linha por obra, número do lote na *Bill Reference*
   (`Impostos de Direitos Autorais/NNN`) e os contratos/contas de origem na
   *Payment Reference*.
3. As contas ficam **vinculadas por campos relacionais**, então o vínculo
   sobrevive a qualquer combinação de rascunho/postado.

Se a conta do autor for **cancelada** ou **excluída**, sua parcela é removida da
conta de imposto acumulada automaticamente. Botões permitem abrir a conta de
imposto a partir da conta do autor e vice-versa.

O percentual de IRRF do autor pode ser definido no cadastro do contato
(**IRRF (%)**, ver seção seguinte).

---

## 12. Prestação de contas ao autor

> Disponível a partir da camada **Author Reports**.

### Página do autor (Beneficiários)

**Copyright › Beneficiaries** lista os contatos que são beneficiários de ao menos
uma linha de royalty (`is_edlab_author`). No formulário do contato, uma página
**Autor** reúne:

- Dados pessoais/bancários usados na prestação de contas: **Birth Date**, **RG**,
  **PIS**, **Nationality**.
- **IRRF (%)** — percentual de retenção do autor.
- **Royalty Lines** — as linhas de royalty em todos os contratos.
- **Open Royalties** — saldo em aberto do autor.
- **Last Statement Sent** — data da última prestação de contas enviada.

### Emitir a prestação de contas

No formulário do autor, botão **Prestação de contas** (abre um assistente):

1. Escolha os **beneficiários** e a **data final (End Date)** do período — apenas
   os royalties acumulados **até essa data** entram.
2. **Print** — gera o **PDF** da prestação de contas: consolida, por autor, os
   royalties do período em todos os contratos e obras, uma linha por obra/canal,
   com a dedução do **IRRF** e o **valor líquido a receber**.
3. **Send** — envia por **e-mail** a cada autor o PDF anexado. Requer que o autor
   tenha e-mail cadastrado. O envio é registrado no **chatter** do autor,
   anotado em cada contrato envolvido, e a **data da última prestação** é gravada
   com o fim do período.

---

## 13. Automações (tarefas agendadas)

O conjunto instala rotinas (**cron**) que rodam diariamente:

| Rotina | O que faz |
|--------|-----------|
| **Atualizar estados de contrato** | Marca como *Expired* os contratos vencidos; **auto-renova** os marcados como *Auto-Renewable* (estendendo pelo *Renewal Term* até voltar a vigorar) e registra no chatter. |
| **Lembretes de vencimento** | Cria uma atividade *A Fazer* para o responsável dos contratos que vencem dentro da janela configurada (padrão 45 dias). Idempotente: não duplica o lembrete. |
| **Reclassificar contas de royalty** | Move os royalties que ultrapassaram o prazo (*Liability After (months)*) da **conta de despesa** para a **conta de passivo** (e vice-versa). |

---

## 14. Fluxo completo — passo a passo

1. **Configurar** as camadas instaladas (plano analítico, contas, produto de
   pagamento, diário, tabela IRRF, contato do governo, percentuais).
2. **Criar o contrato** (assinatura, vencimento, responsável, tags) e
   **validá-lo**.
3. Na aba **Royalties**, adicionar as linhas **beneficiário × obra**, definir as
   **faixas de tiragem** e os **adiantamentos**.
4. **Create Analytic Accounts** para gerar as contas analíticas (e lançar os
   adiantamentos recuperáveis).
5. Conforme as **vendas** são faturadas e pagas, rodar **Fill Royalty Lines**
   (ou **Generate Royalty Analytic Lines** nas faturas) para apurar os royalties.
6. Conferir o saldo em **Reports › Royalty Debts** e **Open Royalties** no
   contrato.
7. **Generate Royalty Bills** para criar as contas a pagar dos autores; pagá-las
   em **Bills › To Pay**.
8. Ao postar as contas, o **IRRF** é retido e acumulado na conta ao governo;
   recolher no vencimento configurado.
9. Emitir a **Prestação de contas** (Print/Send) para cada autor no período.
10. Deixar as **rotinas diárias** cuidarem de vencimentos, renovações e
    reclassificação de contas.

---

## 15. Glossário

| Termo | Significado |
|-------|-------------|
| **Beneficiário** | Autor, tradutor ou ilustrador que recebe royalties. |
| **Obra (Work)** | Produto (livro) sobre o qual incidem os royalties. |
| **Linha de royalty** | Combinação única beneficiário × obra dentro de um contrato. |
| **Faixa (Tier)** | Intervalo de tiragem acumulada com um percentual de royalty. |
| **Adiantamento recuperável** | Valor já pago ao autor, recuperado pelos royalties futuros antes de gerar saldo. |
| **Conta analítica** | Conta que acumula, por beneficiário/obra, o que foi apurado e pago. |
| **Lançamento de corte** | Lançamento que quita os royalties apurados até a data do último pagamento. |
| **Venda especial** | Venda de equipe especial com desconto qualificado; royalty sobre o valor líquido. |
| **Conta a pagar (bill)** | Vendor bill que paga o autor pelos royalties em aberto. |
| **IRRF** | Imposto de renda retido na fonte sobre o pagamento ao autor. |
| **Prestação de contas** | Relatório (PDF/e-mail) consolidando royalties, IRRF e líquido do período por autor. |
| **User / Administrator** | Grupos de acesso; só o Administrator edita a data do último pagamento manualmente. |

---

*Documento gerado para a suíte Copyright Contracts (EdLab Press), Odoo 19.*
