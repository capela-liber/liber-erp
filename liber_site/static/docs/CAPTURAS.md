# Roteiro de capturas de tela dos Manuais

Cada manual em `liber_site/static/docs/` marca os pontos de ilustração com um quadro
tracejado **"📷 Tela a inserir"** que diz o nome exato do arquivo esperado. Para preencher:

1. Capture a tela no Odoo (banco com dados de demonstração, interface em **pt-BR**, janela ~1440 px de largura, sem abas/bookmarks do navegador).
2. Salve o PNG em **`liber_site/static/docs/img/`** com o nome exato listado abaixo.
3. Recarregue a página do manual — a imagem entra no lugar do quadro sozinha, com zoom ao clique. Nada mais a editar.

URLs das páginas (site publicado ou instância local):

- Local: `http://localhost:8069/liber_site/static/docs/<página>`
- Índice: `http://localhost:8069/liber_site/static/docs/index.html`

Total de capturas: 37 · Feitas: marque a caixa ao concluir.


## Acordos de consignação — `liber_soc_agreements.html`

Página: `/liber_site/static/docs/liber_soc_agreements.html`

- [x] **`doc-liber_soc_agreements-form.png`**
  - O que capturar: Formulário de um contrato de consignação ativo, com os botões Ativar/Suspender/Encerrar no topo e o contador 'Na prateleira'
  - Legenda no manual: O contrato de consignação: dados comerciais à esquerda, frequência do acerto e prateleira à direita, e o botão inteligente Na prateleira mostrando o saldo atual no cliente.
- [x] **`doc-liber_soc_agreements-shelf.png`**
  - O que capturar: Lista do estoque na prateleira de um cliente, agrupada por produto, aberta pelo botão 'Na prateleira'
  - Legenda no manual: O saldo da prateleira: cada linha é um título que está fisicamente na livraria, mas ainda pertence à editora.


## Remessas e retornos — `liber_soc_moves.html`

Página: `/liber_site/static/docs/liber_soc_moves.html`

- [x] **`doc-liber_soc_moves-pedido-c.png`**
  - O que capturar: Pedido C confirmado, mostrando o campo Tipo de Consignação, o contrato resolvido e a entrega COM/ no botão inteligente
  - Legenda no manual: O Pedido C: mesmo formulário do pedido de venda, mas com código C, contrato resolvido automaticamente e entrega na série COM/.
- [x] **`doc-liber_soc_moves-cr.png`**
  - O que capturar: Documento CR em estado Aguardando, com os botões Confirmar e Liberar para Logística e a aba Produtos com linhas de devolução
  - Legenda no manual: O CR: confirmado, ele espera o combinado com a livraria; liberado, vira uma transferência RET/ para o armazém processar.
- [x] **`doc-liber_soc_moves-razao.png`**
  - O que capturar: Relatório Razão em pivô, clientes nas linhas e meses nas colunas, com a quantidade consignada líquida
  - Legenda no manual: O Razão: a evolução da consignação de cada cliente, mês a mês, somando remessas e subtraindo retornos e vendas acertadas.


## Acerto de consignação — `liber_soc_settlement.html`

Página: `/liber_site/static/docs/liber_soc_settlement.html`

- [x] **`doc-liber_soc_settlement-kanban.png`**
  - O que capturar: Quadro kanban das operações de consignação com colunas A Fazer, Fazendo e Feito, cartões por cliente com valor e responsável
  - Legenda no manual: O quadro de operações: cada cartão é a rodada de acerto de um cliente, andando pelas colunas A Fazer → Fazendo → Feito.
- [x] **`doc-liber_soc_settlement-linhas.png`**
  - O que capturar: Linhas da operação de consignação com as colunas Em mãos, Vendas, Mapa, Acerto, Alvo, Reposição, Devolução e a etiqueta de Situação
  - Legenda no manual: A tela do acerto: contexto à esquerda (Em mãos, Vendas, Mapa), decisão à direita (Acerto, Reposição, Devolução) e a saúde de cada título na ponta.
- [x] **`doc-liber_soc_settlement-ruptura.png`**
  - O que capturar: Relatório Ruptura em pivô, agrupado por natureza (Estoque, Manual, Falta, Tempo) e cliente, com a soma de exemplares faltantes
  - Legenda no manual: Ruptura com causa: quantos exemplares faltaram, onde, e — o que importa para agir — por quê.


## Fiscal da consignação — `liber_soc_fiscal_br.html`

Página: `/liber_site/static/docs/liber_soc_fiscal_br.html`

- [x] **`doc-liber_soc_fiscal_br-gerar-nota.png`**
  - O que capturar: Pedido C confirmado com o botão Gerar nota no lugar do Criar fatura, e o botão inteligente Nota mostrando 'A emitir'
  - Legenda no manual: O Pedido C confirmado: em vez de "Criar fatura", o botão Gerar nota — e o indicador Nota dizendo se a remessa já foi emitida.


## Auditoria pelo XML — `liber_soc_audit.html`

Página: `/liber_site/static/docs/liber_soc_audit.html`

- [x] **`doc-liber_soc_audit-linhas.png`**
  - O que capturar: Auditoria calculada com linhas divergentes destacadas, colunas Esperado, Mapa e Diferença, e a coluna Resolução por linha
  - Legenda no manual: A reconciliação: o que o fiscal diz (Esperado) contra o que a prateleira mostra (Mapa), com a Diferença destacada e a Resolução a decidir por linha.
- [x] **`doc-liber_soc_audit-ajuste.png`**
  - O que capturar: Movimento de ajuste gerado pela auditoria, com deltas positivos e negativos por título e o lançamento contábil de valor vinculado
  - Legenda no manual: O ajuste materializado: cada delta corrige a prateleira pelo estoque, e a diferença de valor vira um lançamento contábil rastreável.


## Contratos de direitos autorais — `liber_copyright_contracts.html`

Página: `/liber_site/static/docs/liber_copyright_contracts.html`

- [x] **`doc-liber_copyright_contracts-form.png`**
  - O que capturar: Formulário de um contrato de direitos autorais, com datas, prazo de renovação e a aba de direitos autorais
  - Legenda no manual: O formulário do contrato: datas e renovação à esquerda, responsável e arquivo à direita, e as linhas de royalty na aba abaixo.
- [x] **`doc-liber_copyright_contracts-partner.png`**
  - O que capturar: Cadastro de um contato com o botão inteligente Contratos e a aba listando os contratos em que ele é favorecido
  - Legenda no manual: No contato do autor, o botão Contratos abre tudo em que ele é favorecido.


## Cálculo de royalties — `liber_copyright_contracts_analytics.html`

Página: `/liber_site/static/docs/liber_copyright_contracts_analytics.html`

- [x] **`doc-liber_copyright_contracts_analytics-wizard.png`**
  - O que capturar: Assistente Criar Contas Analíticas listando os favorecidos do contrato com o nome sugerido de cada conta
  - Legenda no manual: O assistente de criação: uma linha por favorecido × obra, com o nome padrão já montado.
- [x] **`doc-liber_copyright_contracts_analytics-debts.png`**
  - O que capturar: Relatório Dívidas de Royalties em visão pivô, com Provisionado, Pago e Saldo por favorecido e ano
  - Legenda no manual: Dívidas de Royalties: o provisionado, o pago e o saldo de cada favorecido, ano a ano.


## IRRF sobre direitos — `liber_copyright_contracts_taxes.html`

Página: `/liber_site/static/docs/liber_copyright_contracts_taxes.html`

- [x] **`doc-liber_copyright_contracts_taxes-mode.png`**
  - O que capturar: Aba Favorecido do contato com o Modo de IRRF em botões de opção: Tabela Progressiva, Percentual Manual e Isento
  - Legenda no manual: O modo de IRRF no cadastro do favorecido: tabela, percentual fixo ou isenção.
- [x] **`doc-liber_copyright_contracts_taxes-batch.png`**
  - O que capturar: Fatura acumuladora do IRRF com uma linha por obra e a referência Impostos de Direitos Autorais/001
  - Legenda no manual: O lote do imposto: uma linha por obra, referência com o número do lote e as origens listadas na referência de pagamento.


## Pagamento de royalties — `liber_copyright_contracts_payments.html`

Página: `/liber_site/static/docs/liber_copyright_contracts_payments.html`

- [x] **`doc-liber_copyright_contracts_payments-bill.png`**
  - O que capturar: Fatura de fornecedor gerada para um autor, com uma linha por obra e a referência contrato · favorecido
  - Legenda no manual: A fatura do autor: uma linha por obra com saldo, vencimento pelo prazo configurado e o contrato de origem no cabeçalho.


## Prestação de contas — `liber_copyright_contracts_reports.html`

Página: `/liber_site/static/docs/liber_copyright_contracts_reports.html`

- [x] **`doc-liber_copyright_contracts_reports-author.png`**
  - O que capturar: Aba Favorecido do contato: identificação, IRRF, contas bancárias e as linhas de royalty com saldo
  - Legenda no manual: A página do autor: tudo o que o extrato usa, num lugar só.
- [x] **`doc-liber_copyright_contracts_reports-pdf.png`**
  - O que capturar: PDF da prestação de contas: resumo com período, valor total, IRRF e valor a receber, seguido da tabela de obras
  - Legenda no manual: O extrato do autor: resumo no topo, depois obra por obra, faturas, vendas especiais e adiantamentos.


## Importação de XML de NF-e — `liber_nfe_xml.html`

Página: `/liber_site/static/docs/liber_nfe_xml.html`

- [x] **`doc-liber_nfe_xml-lista.png`**
  - O que capturar: Lista do painel NFe XML com colunas de direção, chave de acesso, cliente, número e valor da DANFE e situação
- [x] **`doc-liber_nfe_xml-form.png`**
  - O que capturar: Formulário de uma nota no painel NFe XML, com dados fiscais do emitente e destinatário, chave de acesso e a lista de itens extraída do XML
- [x] **`doc-liber_nfe_xml-sefaz.png`**
  - O que capturar: Lista de varreduras SEFAZ com data, empresa, situação e contadores de documentos, NF-e importadas e cancelamentos


## Notas de remessa — `liber_nfe_remessa.html`

Página: `/liber_site/static/docs/liber_nfe_remessa.html`

- [x] **`doc-liber_nfe_remessa-lista.png`**
  - O que capturar: Lista de remessas com número REM, data, destinatário, origem da remessa, documento de origem e total
- [x] **`doc-liber_nfe_remessa-form.png`**
  - O que capturar: Formulário de uma nota de remessa confirmada, com a faixa Simples remessa e o botão que abre a baixa automática


## Integração Metabooks — `liber_metabooks_integration.html`

Página: `/liber_site/static/docs/liber_metabooks_integration.html`

- [x] **`doc-liber_metabooks_integration-settings.png`**
  - O que capturar: Página de configurações do Metabooks com usuário, senha, código de autorização e o botão Testar conexão
- [x] **`doc-liber_metabooks_integration-job.png`**
  - O que capturar: Registro de importação de catálogo com progresso, total de livros, páginas e situação Em execução
- [x] **`doc-liber_metabooks_integration-envio.png`**
  - O que capturar: Formulário de um envio para a Metabooks com os botões Buscar alterações, Verificar e Gerar planilha, e a aba de alterações com colunas Antes e Depois


## Bonificação — `liber_product_bonus.html`

Página: `/liber_site/static/docs/liber_product_bonus.html`

- [x] **`doc-liber_product_bonus-import.png`**
  - O que capturar: Assistente de importação com a prévia: contatos existentes, novos, repetidos e sem endereço, antes de gravar.
  - Legenda no manual: A prévia da importação: nada é gravado antes do "Importar".
- [x] **`doc-liber_product_bonus-triage.png`**
  - O que capturar: Tela de triagem do disparo: fontes que somam, tabela de candidatos com Score e endereço, e o contador de meta se movendo.
  - Legenda no manual: A triagem: o freio é o contador vivo, não um "não" na hora de salvar.
- [x] **`doc-liber_product_bonus-analysis.png`**
  - O que capturar: Tabela dinâmica de análise cruzando investimento, resultado e custo.
  - Legenda no manual: Análise: o que cada verba gastou e o que voltou.


## Orçamento — `liber_budget.html`

Página: `/liber_site/static/docs/liber_budget.html`

- [x] **`doc-liber_budget-lines.png`**
  - O que capturar: Formulário do orçamento com as linhas: Planned, Theoretical e Practical lado a lado, linhas em vermelho abaixo do planejado.
  - Legenda no manual: As linhas do orçamento: planejado, teórico e realizado lado a lado, com drill-down por linha.


## Arquivos no Dropbox — `liber_dropbox.html`

Página: `/liber_site/static/docs/liber_dropbox.html`

- [x] **`doc-liber_dropbox-files.png`**
  - O que capturar: Lista de Arquivos com o painel de pastas à esquerda, colunas de tags, contatos e produto, e os botões de baixar e compartilhar por linha
  - Legenda no manual: A tela de Arquivos: pastas no painel à esquerda — cada pessoa só vê as suas —, vínculos nas colunas e as ações em cada linha.
- [x] **`doc-liber_dropbox-folder.png`**
  - O que capturar: Formulário de uma pasta com caminho, a opção Incluir subpastas e os grupos de Leitura e Escrita preenchidos
  - Legenda no manual: O mapeamento da pasta: o caminho no Dropbox à esquerda, e à direita a decisão que importa — quem lê, quem escreve.
- [x] **`doc-liber_dropbox-share.png`**
  - O que capturar: Ficha de um arquivo compartilhado, com Link compartilhado, Compartilhado por, Compartilhado em e Link expira em preenchidos
  - Legenda no manual: O razão do compartilhamento: o link, quem pediu, quando — e a data em que ele morre.
- [x] **`doc-liber_dropbox-partner.png`**
  - O que capturar: Ficha de um contato com o botão inteligente do Dropbox mostrando a contagem de arquivos vinculados
  - Legenda no manual: No contato do autor: os contratos dele no Dropbox, a um clique — contados conforme a permissão de quem olha.


## Papéis de acesso — `liber_roles.html`

Página: `/liber_site/static/docs/liber_roles.html`

- [x] **`doc-liber_roles-user.png`**
  - O que capturar: Ficha do usuário com a seção Liber / Funções: um seletor por departamento, com os níveis Assistente e Gerente.
  - Legenda no manual: A ficha do usuário: uma função por departamento, e o resto se deriva.
