# Módulo `capela_ai` — notas de concepção

> O agente da casa: conversa, consulta o que a pessoa já podia consultar, e
> **propõe** mudanças que um humano aprova.
> Desenho e primeira fatia de 2026-07-27.
>
> **Ressalva honesta, e ela vale a leitura:** este código **nunca rodou**. Foi
> escrito sem Odoo instalado na máquina, sem banco e sem os testes terem sido
> executados uma vez sequer. A seção 7 lista as APIs do Odoo 19 de que eu não
> tenho certeza. Trate isto como um desenho executável em revisão, não como
> software entregue — e rode os testes antes de acreditar em qualquer frase
> afirmativa deste arquivo.

---

## 1. O problema, e por que a resposta óbvia não serve

Colocar um LLM dentro de um ERP é fácil de fazer errado de um jeito específico:
dar a ele uma credencial de serviço e um par de funções `search`/`write`, e
confiar no prompt para segurar o resto. Funciona na demonstração e quebra no
primeiro pedido cujo chatter contenha um e-mail de cliente dizendo "ignore as
instruções anteriores".

O problema não é o cliente mal-intencionado — é que **o texto que o modelo lê e
o texto que o instrui são o mesmo texto**. Nenhuma quantidade de instrução no
prompt resolve isso, porque a instrução compete em pé de igualdade com o
conteúdo. Então a fronteira de segurança não pode morar lá.

## 2. Três decisões, e tudo o mais decorre

**O agente é um usuário, nunca um serviço.** Toda operação de ORM roda como
`env.user`. Não há `sudo()` em `tools/`, e `tests/test_no_sudo.py` quebra o
build se aparecer um. Com isso a matriz do `liber_roles` vale de graça: um
assistente de marketing pedindo lançamento contábil ao agente toma `AccessError`
do ORM, não de uma frase. O raio de ação do agente **não consegue** exceder o da
pessoa, aconteça o que acontecer no prompt.

**O catálogo de ferramentas É o conjunto de capacidades.** Não existe "execute
este domain e grave estes campos". Existem ferramentas nomeadas, declaradas em
Python, com esquema. `unlink` não está entre elas — e o que não é método
chamável, nenhum prompt inventa. Para desfazer há cancelar e arquivar.

**Planejar e aplicar são atos separados.** A ferramenta de escrita não escreve:
devolve um plano enumerado que a interface mostra e um humano aprova.
`action_approve()` **não recebe parâmetro nenhum** — executa as linhas já
gravadas, conferindo um SHA-256. Entre a proposta e a execução não passa texto
de modelo. É essa assinatura vazia que fecha o caminho "injeção → aprovar outra
coisa".

## 3. Massa contra enumerado

O pedido original era "criar 4 S000 diferentes para essa lista de pedidos" — e
ao mesmo tempo "nunca ação em massa em grid". Não é contradição: o que separa os
dois casos não é a quantidade, é a **proposta nomear cada documento antes**.

Quatro linhas de plano, quatro frases em português, um botão: passa. O outro
caminho simplesmente não é exprimível, porque não existe linha de plano que
signifique "e o resto também". `search(domain).write(...)` não tem como ser
dito.

## 4. A interseção tripla

O que um agente pode fazer por você não está em lista nenhuma isoladamente:

```
ferramentas do agente
  ∩ ferramentas concedidas às suas funções   (res.groups)
  ∩ o que o ORM deixaria você fazer com as mãos
```

As duas primeiras são calculadas em `capela_ai_agent.py` e definem o que vai no
parâmetro `tools` da API — o modelo **nem enxerga** o que não pode chamar. A
terceira não é calculada por ninguém: acontece sozinha porque tudo roda como a
pessoa. É a mais forte justamente por não depender de nós lembrarmos dela.

Tetos por nível: Assistente 10, Gerente 50, Direção 50, Visitante 0. Moram em
`res.groups` e são escolhidos pelo `capela_ai_roles`, não pelo núcleo.

## 5. Por que dois módulos

`capela_ai` **não depende** de `liber_roles`. O núcleo oferece o mecanismo
(campos em `res.groups`); a ponte `capela_ai_roles` escolhe os números para as
funções da casa. Não é purismo de engenharia, é o modelo de negócio: o `liber_*`
é o que se libera e o `capela_*` é o que se vende, e um agente que só instala
onde já existe o `liber_roles` não pode ser vendido para quem usa os perfis
nativos do Odoo.

## 6. As fronteiras que este módulo NÃO cobre

**`sudo()`.** O guarda em `ir.model.access.check` deixa passar quem grava como
superusuário. Não é descuido: ao criar um pedido o Odoo incrementa
`ir.sequence`, insere `mail.message` e mexe em `mail.followers` por baixo do
usuário — bloquear isso quebraria o ato que se quer permitir. A defesa contra
`sudo` é `tests/test_no_sudo.py` e a revisão, não o ORM. Vale saber qual das
duas está segurando o quê.

**Chamada de método.** O motor de plano sabe criar e alterar. Não sabe chamar
`action_confirm`. Então **confirmar pedido não é possível hoje** — e isso é uma
lacuna real, não um esquecimento. Suportar exigiria uma quarta operação com
allowlist de `(modelo, método)` declarada pela ferramenta, e essa é uma decisão
de desenho que merece calma: é a porta por onde a arbitrariedade voltaria a
entrar. Confirmação, aliás, é o caso de uso da automação, que ficou para a v2.

**Concorrência.** Um plano guarda `res_id` no momento da proposta. Se alguém
alterar o documento entre a proposta e a aprovação, o plano aplica por cima sem
perceber. O hash protege contra o plano ser adulterado, não contra o mundo ter
mudado. Falta um carimbo de `write_date` por linha.

**Não há conector.** Nada aqui fala com a API do Claude ainda, e não há
interface. É deliberado: a metade arriscada do produto é a contenção, e ela é
testável sem chave de API e sem tela. Conector e superfície são a próxima fatia.

## 7. APIs do Odoo 19 a conferir antes de confiar

Escrevi sem poder importar `odoo`. Estas quatro são as que eu chutei com mais
confiança do que gostaria:

| Onde | O quê | Risco |
|---|---|---|
| `tools/query.py` | `_read_group(domain, groupby=, aggregates=, limit=, order=)` | `read_group` público saiu no 18; a forma privada mudou de assinatura entre versões |
| `models/capela_ai_tool.py` | `ir.model.data._update_xmlids([{...}])` | existe desde o 15, mas confira o nome dos campos do dict |
| `models/capela_ai_tool.py` | `init()` ser chamado a cada upgrade | se não for, a sincronização não roda e o módulo sobe sem ferramenta nenhuma |
| `models/capela_ai_plan.py` | `env.cr.savepoint()` como gerenciador de contexto | é o que garante o tudo-ou-nada |

O que **sei** que está certo, porque conferi no repositório: a convenção de
`res.groups.privilege` / `privilege_id` do 19 (copiada do `liber_roles`), e a
técnica de cortar em `ir.model.access.check` (idem).

## 8. O que vem depois

1. **Rodar os testes.** Antes de qualquer linha nova.
2. **Conector.** SDK `anthropic`, laço manual (não o tool runner: a aprovação é
   assíncrona, o humano clica minutos depois — um laço síncrono não serve).
   Conversa persistida em `capela.ai.conversation`.
3. **Superfície.** Menção no chatter (`@Agente Comercial` num S000) entrega o
   registro como contexto e é o caminho mais barato para "ajuda em contexto".
4. **Cartão de aprovação.** A tela que mostra o plano. Hoje o motor existe e
   ninguém consegue clicar em nada.
5. **`capela_ai_automation`** (v2). A UX está desenhada — máquina de estados
   Rascunho → Sombra → Armada → Pausada, diário com calibragem por ✓/✗, portão
   de armar por taxa de acerto. Três coisas que a v1 já deixou prontas para
   ela: o motor de plano roda destacado de uma conversa, `automation_safe`
   existe desde o começo no registro de ferramentas, e a auditoria não
   pressupõe turno de usuário.

## 9. Sobre o cache de prefixo

A ordem de renderização da API é `tools` → `system` → `messages`, e o cache é
casamento exato de bytes. Como a lista de ferramentas deriva de grupos — logo é
determinística para um par (agente, pessoa) — o prefixo é estável e a conversa
inteira lê cache a ~0,1× do preço.

Isso só continua verdade se **nada volátil entrar no `system_prompt`**: nem
data, nem nome de usuário, nem id de sessão. Esses vão em `messages`, depois do
ponto de corte. É uma regra de código, não uma otimização a fazer depois — uma
`datetime.now()` no lugar errado zera a economia inteira e ninguém percebe,
porque nada quebra.
