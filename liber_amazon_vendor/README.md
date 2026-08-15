# Amazon Vendor Central

Lê os pedidos da Amazon e os transforma em cotação. Só isso — e a limitação é
o desenho, não a fase.

## A inversão que dá nome à confusão

No Vendor Central **a Amazon compra**. O que a SP-API chama de `purchaseOrder`
é o pedido *dela*; do nosso lado é uma **venda**. Por isso o que sai deste
módulo é `sale.order`, nunca `purchase.order` — trocar os dois inverteria
estoque e faturamento, e o erro só apareceria no fechamento.

## O que ele não faz, e não vai fazer aqui

Não confirma pedido (*acknowledgement*), não manda ASN, não imprime etiqueta
de caixa, não emite invoice por EDI. Essas etapas disparam relógio de SLA na
Amazon e são compromisso de entrega: pertencem a uma pessoa olhando, não a um
cron rodando às quatro da manhã.

A restrição é estrutural, não uma promessa em comentário:

- `services/api.py` tem um único caminho para a SP-API, `_get`, que só sabe
  fazer GET.
- O único `POST` do arquivo é a troca do refresh token, e vai para
  `api.amazon.com` — o servidor de login, que não conhece pedido nenhum.
- `tests/test_api.py::test_module_has_no_write_path_to_amazon` lê o próprio
  código-fonte e falha se alguém acrescentar um verbo de escrita.

Do lado do Odoo, a mesma disciplina: a cotação nasce em rascunho e fica lá.
`test_quotation_is_never_confirmed` cai se algum dia aparecer um
`action_confirm` por conveniência.

## Por que existe um espelho em vez de importar direto para `sale.order`

Porque o pedido muda depois de criado. Na conta real, 100% dos pedidos chegam
já `Acknowledged` ou `Closed`: alguém confirma no portal da Amazon, na mão, e
o Vendor Central é hoje o sistema de registro do estado. Além disso a Amazon
aceita pedido parcial com frequência, e a quantidade confirmada raramente é a
pedida.

Daí três decisões:

1. **A importação relê uma janela**, em vez de andar com uma marca d'água.
   `Re-read Window (days)` na conta diz quanto ela recua.
2. **Reimportar é idempotente.** A chave é (número do PO, conta).
3. **Mudança depois da cotação não reescreve nada.** O módulo marca a
   divergência, mostra em vermelho, e espera que uma pessoa decida. O
   documento comercial pertence a quem o fez.

## Casamento de título

O ISBN vem de `vendorProductIdentifier` — o identificador que *nós* demos ao
título — e casa com o `barcode` do `product.product`. O `amazonProductIdentifier`
é o ASIN, código interno da Amazon, e não existe no nosso cadastro.

A comparação normaliza hífen e espaço dos dois lados, porque parte do catálogo
está gravada com hífen. Sem isso, título cadastrado apareceria como ausente.

Linha cujo ISBN não casa **não impede nada**: ela entra sem produto, é contada
e fica de fora da cotação. Travar o pedido inteiro por causa de um título que
talvez nem seja nosso seria pior, e a Amazon não espera.

O que não pode é sumir em silêncio — a cotação passa a prometer menos
exemplares do que foi pedido. Por isso, toda vez que uma linha fica de fora, o
histórico do pedido registra os ISBNs deixados. Quem quiser trazê-los de volta
cadastra o título ou escolhe o produto à mão na linha, e essa escolha sobrevive
às próximas leituras (`Product Locked`).

Só se recusa a cotação quando **nenhuma** linha casou: não há o que cotar.

O preço da linha é o **netCost** (o que a Amazon paga), nunca o `listPrice`
(a etiqueta com que ela revende).

## As unidades da Amazon

Cada centro de distribuição compra como um estabelecimento fiscal próprio, e o
pedido o nomeia só pela sigla: `{"partyId": "GRU8"}`. Sem CNPJ, sem endereço —
a especificação da SP-API prevê `taxInfo` e `address`, a Amazon não os
preenche.

Por isso o mapa `liber.amazon.unit`: sigla → cliente (e endereço de entrega,
quando difere). Unidade não mapeada não vira cotação — cair num cliente padrão
emitiria a nota contra o CNPJ da filial errada, em silêncio.

O botão **Mapear unidades pelos pedidos** semeia o mapa com as siglas já
vistas e sugere um cliente quando um contato casa sem ambiguidade. É sugestão
de tela, não regra: casar por nome só funciona em quem batize os contatos de
"Amazon GRU8".

## Configurar

1. **Aplicativos → Amazon Vendor → Configuração → Contas → Novo**
2. Nome, região (`BR` — o Brasil é atendido pelo host da América do Norte; não
   existe host "br"), e **Amazon como cliente**: o parceiro em nome de quem as
   cotações são feitas.
3. As credenciais só aparecem para administrador do sistema: `client_id`,
   `client_secret` e `refresh_token` do app no Developer Central. Com o
   refresh token se obtém acesso a tudo que o app autoriza — quem opera não
   precisa dele e não o vê.
4. **Testar conexão**. Ele fala com a Amazon e não importa nada.

O cron diário (`Amazon Vendor: read purchase orders`, 07:00 UTC) já vem ativo.
Ele varre as contas cadastradas — recém-instalado não existe nenhuma, então
ele não faz nada até alguém configurar a primeira.

## Usar

**Importar da Amazon** abre o assistente: escolhe a janela, **lê**, e mostra a
conta antes de gravar — quantos pedidos, quantos exemplares, quanto dinheiro,
e a lista exata dos ISBNs que não casam. Só então **Importar**.

No pedido importado, **Gerar cotação** cria o `sale.order` em rascunho.

Dois relatórios respondem perguntas diferentes: **Agenda de entregas** é por
pedido — o que vence quando, o que já venceu. **Análise por título** é por
livro — o que não foi atendido (e se a culpa é do cadastro ou de quem opera),
e quanto tempo o ciclo levou. A coluna **Situação no Odoo** separa o que ainda dá para atender
do que a Amazon já fechou. O nome é literal: "cotado aqui" conta só o que
passou por este módulo, e como o histórico foi importado depois do fato,
quase nada antigo aparece cotado — aqueles livros saíram pelo portal. Para o
período importado, "janela fechada" é o normal, não perda. Para tempo de ciclo, ligue *Ciclo concluído*:
pedido aberto vale zero e dilui a média.

## Erros que valem reconhecer

- **HTTP 403 com o login tendo funcionado** não é credencial errada. É o app
  sem o papel de *Vendor Orders* no Developer Central, ou autorização feita
  para Seller Central em vez de Vendor. Ajuste no painel da Amazon.
- **Moeda diferente da empresa** faz a cotação ser recusada em vez de
  convertida. Converter caladamente poria um número plausível e errado num
  documento que ninguém iria reconferir.

## Dependências

Nenhuma nova. Desde 2023 a SP-API não exige assinatura AWS SigV4 nem role IAM:
o access token do LWA no header é a credencial inteira, e `requests` — que o
Odoo já tem — basta. As variáveis `AWS_*` que aparecem em configurações
antigas de integração com a Amazon são resquício.

## Testes

```
odoo -d <base_de_teste> -i liber_amazon_vendor --test-enable \
     --test-tags amazon_vendor --stop-after-init
```

112 testes. A tradução pura (datas, ISBN, netCost) também roda fora do Odoo,
em milissegundos, por `scripts/tests/test_amazon_vendor.py`.
