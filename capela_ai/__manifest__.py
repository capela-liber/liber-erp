# -*- coding: utf-8 -*-
{
    'name': 'Capela AI (o agente da casa)',
    'version': '19.0.1.0.0',
    'summary': 'Claude dentro do Odoo: consulta, redige e propõe — nunca varre nem apaga',
    'description': """
Um agente que conversa no Odoo, lê o que o usuário pode ler e PROPÕE mudanças
que um humano aprova. Três decisões carregam o módulo inteiro:

1. O agente é um usuário, nunca um serviço.
   Toda operação de ORM roda como `env.user`. Não há `sudo()` no código de
   ferramenta -- e há um teste que quebra o build se aparecer um. Assim a
   matriz de acesso da casa (grupos, record rules, ACLs) vale de graça: um
   assistente de marketing pedindo lançamento contábil ao agente toma
   AccessError do ORM, não de uma frase no prompt. O prompt NUNCA é a
   fronteira de segurança; se fosse, bastaria um PDF de fornecedor dizendo
   "ignore as instruções anteriores" para virar o sistema do avesso.

2. O catálogo de ferramentas É o conjunto de capacidades.
   Não existe ferramenta "execute este domain e grave estes campos". Existem
   ferramentas nomeadas, com assinatura, declaradas em Python. `unlink` não
   está entre elas -- e o que não é método chamável nenhum prompt inventa.
   Para desfazer existe cancelar e arquivar, que é o idioma do Odoo.

3. Planejar e aplicar são dois atos separados.
   A ferramenta de escrita não escreve: devolve um PLANO enumerado, registro a
   registro, que a interface mostra e um humano aprova. A aprovação executa o
   plano ARMAZENADO, por id, conferindo um hash do conteúdo -- nunca reenviando
   o que o modelo mandou. É isso que fecha o caminho "injeção -> aprovar outra
   coisa": entre a proposta e a execução não há texto de modelo nenhum.

A diferença que importa não é quantos registros, é ENUMERADO contra VARRIDO.
Criar quatro orçamentos nomeados um a um, vistos antes: passa. Um
`search(domain).write(...)` não tem como ser expresso.

Tetos por nível (registros por plano) e quais ferramentas cada função pode
chamar são dados, não código: ficam em `res.groups`, configuráveis só por
administrador em modo desenvolvedor. Este módulo NÃO depende de `liber_roles`
-- ele oferece o mecanismo. Quem casa o mecanismo com as funções da casa é o
`capela_ai_roles`, ao lado.

Fronteira que este módulo NÃO cobre, dita em voz alta: `sudo()`. O guarda em
`ir.model.access.check` deixa passar quem escreve como superusuário, porque é
por lá que o Odoo grava sequências, mensagens de chatter e seguidores ao criar
um documento -- bloquear isso quebraria o próprio ato que se quer permitir.
Contra `sudo()` a defesa é a revisão do código e o teste que procura por ele,
não o ORM. Ver models/ir_model_access.py.
""",
    'author': 'EdLab Press',
    'category': 'Productivity',
    'depends': [
        'base',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/capela_ai_security.xml',
        'data/capela_ai_data.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'OEEL-1',  # produto pago da capela; o liber_* é que é AGPL
}
