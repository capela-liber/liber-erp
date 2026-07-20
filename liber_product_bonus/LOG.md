Só uma coisa não entendi. O que acontece quando um contato não confirma que recebeu (e consequentemente, não queremos mais mandar). Ou melhor: o contato divulgou, divulgou maravilhosamente bem ou meia boca. Como posso ir criando uma maneira simples para que na próxima decisão a gente tenha uma maneira de decidir mais rápida. Pense no contexto de influencers. 

----

E como vc imagina a UX disso? Eu só sei que as necessidades básicas são: 
* tenho que definir um jeito para não sair dando livro a torto e a direito
* também não mandar livro é ruim
* mandar para quem? como filtrar rápido? contatos, jornalistas, lista vip "daquela campanha x"
* mesmo pegando uma lista eu vou ter que decidir se vai ou não vai... 
* e depois de selecionado, podemos mandar mesmo?
* e uma coisa é o marketing/comercial e outra é o que está no contrato. 
* contrato é mais simples. defini-se o número de exemplares e gera-se uma B0000
* e coisas pequenas podem encher o saco
	* importar listas vip
	* fazer etiquetas
	* lembrar de ligar para as pessoas que receberam para saber se chegou


----

>> Importação e emissão de etiquetas em lista vip é algo muito importante, bem como followup para saber se o livro chegou


----

> Consequência prática: o documento de bonificação **nunca** gera fatura de cliente, **nunca**
entra no funil comercial e **sempre** aterrissa num analítico de despesa.
>> No Brasil gera. Qualquer movimentação necessita um XML

>Ele quer saber a % de livros doados numa tiragem. **Não existe nenhum modelo de tiragem no repo**
(zero hits para `tiragem|print_run|impressao`). O mais próximo é metadado bibliográfico do
Metabooks (`edition`, `metabooks_edition_number`) — ONIX descritivo, sem noção de quantidade
impressa.
>>A tiragem é o estoque. Se fiz 3000 mil e quero doar x%, isso tem que ser acompanhado 
e travado. Mas temos razões distintas para doação. Autor (editorial), marketing, comercial. 

>>A questão da nota me preocupa. Temos notas sim. De simples remessa. Por isso um documento do tipo B000 que gera MOV e INV

>>O cuidado com as listas vip é muito importante. Uma lista vip não é uma tag em contatos. 
Ela tem uma história. Quem montou, o que gastou, quem foi o responsável. Ver quem recebeu que livro, o motivo... não podemos mandar todo livro que sai para todas as pessoas. As listas vip geram B000 que são aprovadas pelos seus responsáveis e que devem caber numa meta inicial de doação.

>> Não misturar evento com essa história

>> usar no modelo product em vez de edlab. (edlab está reservado para módulos específicos, como o de migração)
## 18/07 — a nota vira documento separado (REM/)
> "então estamos diante de algo parecido com a SO e as alternativas que criei
> para SOC SSOC etc. Eu ficava tendo que rodear a SO... bastava criar um
> documento totalmente separado. [...] temos que ter uma sequência de INV que
> não gera pagamentos. E assim deixamos a INV só pra o que realmente envolve a
> complexidade de uma venda, com pagamentos, banco etc."

> "REM passaria a ser COM (ligado a consig em logística) e REM passa a ser o
> documento fiscal que nunca tem pagamentos."

E sobre o O15: "há uma forma de configurar isso. Fizemos isso no Odoo 15
utilizando o account mapping [...] E daí a INV não gera pagamento." — o
mecanismo é o edoo_invoice_paid; portado como liber_nfe_remessa (baixa automática,
porque o 19 proíbe a troca da conta do recebível).
