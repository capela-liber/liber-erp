# O ciclo dos royalties — do contrato ao pagamento

O ciclo completo da família `liber_copyright_contracts*`, na ordem em que os
eventos acontecem, com a empresa que age em cada um. HE = a editora
contratante (dona do contrato); EL = a editora irmã que também vende a obra.

## Preparação

1. **HE**: cria o contrato (favorecido × obra, tiers de percentual,
   adiantamento descontável) e o valida.
2. **HE**: cria a conta analítica da linha de royalty (Ação → *Create
   Analytic Accounts*). O adiantamento, se houver, entra como lançamento
   positivo datado da assinatura.
3. **HE**: configura o intercompany nas Definições — EL como empresa de
   origem, produto "Royalties entre Empresas", diários e markup.
4. **HE**: configura o imposto — autoridade fiscal (Receita Federal) e conta
   de passivo "IRRF a Recolher". Sem essa fiação a retenção é pulada em
   silêncio (opt-in por desenho).

## Vendas

5. **EL**: vende a obra — fatura de cliente postada.
6. **EL**: recebe o pagamento da fatura (**só venda paga acrua royalty**).
7. **HE**: vende a obra também, pelas suas próprias faturas pagas.

## Booking (o coração)

8. **HE**: roda **Fill Royalty Lines** no contrato → cada venda paga
   (própria e da EL) vira um lançamento analítico negativo na conta do
   favorecido, com o percentual do tier sobre a quantidade **acumulada** e a
   **empresa de origem** carimbada. Idempotente: a mesma venda nunca é
   lançada duas vezes. O extrato fica visível na ficha da conta analítica
   (botão "Margem bruta") e no relatório *Royalty Debts* (coluna e
   agrupamento por Empresa de Origem).
9. **HE**: no fim do mesmo booking, a sincronização intercompany cria (ou
   atualiza) a **invoice acumuladora HE→EL em rascunho** — soma dos acúmulos
   de origem EL × (1 + markup). **É um acumulador por par de empresas, não
   por contrato**: contratos diferentes entram como linhas do mesmo rascunho
   (a Referência de Pagamento lista todos: "Contratos: 2010/001, 2026/001").

## Perna intercompany (HE recebe da EL)

10. **HE**: **posta** a invoice HE→EL. Ninguém posta por você: rascunho é
    acumulador vivo; postar é a decisão humana de congelar a cobrança.
11. **EL**: a **bill espelho** nasce automaticamente ao postar (ref = número
    da invoice; smart buttons ⇄ ligam os dois lados). Ela é fatura de
    fornecedor comum da EL — aparece em Faturamento → Fornecedores (com a EL
    ativa no seletor de empresas), **não** nos menus Faturas do app (que
    filtram por contrato).
12. **EL**: posta e paga a bill espelho. **A baixa não atravessa**: cada
    empresa registra o seu lado — a HE registra o recebimento na invoice
    dela (ou concilia pelo extrato) quando a transferência chega. Vendas da
    EL registradas depois do post entram num **par novo** no próximo Fill.

## Prestação de contas ao autor (PDF)

13. **HE**: gera a **Prestação de Contas** do favorecido (*Royalty
    Statement*: escolhe favorecidos e data-corte → PDF, com envio por
    e-mail). O demonstrativo lista, por obra: exemplares, base, percentual e
    o devido; declara o adiantamento recuperado. **O total do PDF é o mesmo
    da bill** que vem a seguir — os dois leem o mesmo analítico.

## Perna do autor (HE paga o favorecido)

14. **HE**: roda **Gerar Faturas de Royalties** → a bill do autor nasce com:
    - a linha bruta de royalties por obra;
    - a linha negativa **"Adiantamento descontado"**, quando houver
      adiantamento a recuperar (a geração escritura o adiantamento no
      analítico antes de calcular — buraco de ordem fechado);
    - a linha negativa **"IRRF retido"**, quando a retenção for maior que
      zero (tabela 2026: nada se retém até R$ 5.000; acima, faixas
      progressivas — ou percentual manual/isento marcado no favorecido).
15. **HE**: no mesmo instante, o **lote de IRRF** (bill para a Receita
    Federal) é criado ou atualizado sozinho — cada bill de autor com
    retenção acumula no lote rascunho do mês, vencimento no dia configurado
    do mês seguinte.
16. **HE**: posta e **paga a bill do autor** → a Data do Último Pagamento é
    carimbada na linha do contrato e o corte assenta o analítico (a conta
    zera até a data). Esse pagamento dispara um booking, que de carona
    re-sincroniza o intercompany.
17. **HE**: posta e paga o **lote de IRRF** → o passivo "IRRF a Recolher" é
    liquidado com o governo.

Daí em diante o ciclo se repete a partir do evento 5: novas vendas → Fill →
par intercompany novo (perna EL) e novo saldo devido → nova prestação de
contas e nova bill (perna do autor).

## Avisos que a prática ensinou

- **Uma obra em dois contratos acrua em dobro**: cada linha de contrato
  aplica o percentual inteiro sobre as mesmas vendas. Co-beneficiários não
  são divididos automaticamente.
- **O seletor de empresas esconde documentos**: com só a HE ativa, nada da
  EL aparece (e vice-versa). Antes de procurar um documento "sumido",
  confira as empresas ativas.
- **A retenção entra na criação da bill**: uma bill rascunho gerada antes de
  configurar o IRRF (ou o adiantamento) não ganha as linhas retroativamente
  — exclua e gere de novo.
- **Postar a invoice do par exige poder ler o diário da EL** — corrigido
  para funcionar com qualquer seleção de empresas, mas o diário de compras
  intercompany da EL precisa ser um diário de compras de verdade, senão o
  espelho cai no diário padrão.
