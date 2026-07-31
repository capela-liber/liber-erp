# -*- coding: utf-8 -*-
{
    'name': "NFe — Emissão pela Focus NFe",
    'summary': "Emite NFe modelo 55 pela API REST da Focus NFe, a partir da fatura",
    'description': """
Emissão de NFe modelo 55 pela Focus NFe.

A OCA não tem a cadeia fiscal no 19 (a branch 19.0 do l10n-brazil traz dez
módulos e nenhum deles emite), e o `l10n_br_nfe_focus` não existe em versão
nenhuma. Então este módulo faz o que sobrava: fala com a Focus direto.

O desenho tem três camadas, e as duas de baixo não conhecem o Odoo:

  focus_client.py   HTTP puro. Basic auth com o token no lugar do usuário e
                    senha vazia. Traduz os códigos da Focus em exceções com
                    mensagem legível — 422 é o caso comum e o mais útil.
  nfe_payload.py    A regra fiscal. Monta o JSON, arredonda em Decimal (float
                    aqui faz a soma dos itens não fechar com o total, que é
                    rejeição na hora), decide CST ou CSOSN pelo regime, e diz
                    o que falta ANTES de gastar uma chamada.
  account_move.py   A fatura. Botões de emitir, consultar e cancelar.

O certificado A1 fica na Focus, não aqui: quem assina e transmite à SEFAZ é o
servidor deles. Do nosso lado só existe o token.

A emissão é assíncrona porque a SEFAZ é assíncrona: o POST devolve
'processando_autorizacao' e a autorização vem numa consulta posterior, feita
pelo botão ou pelo cron de dez em dez minutos.

Autorizada, a chave de acesso vai para `account.move.nfe_key` — o mesmo campo
que o liber_nfe_xml usa para amarrar XML e fatura. Uma nota que emitimos e uma
nota que recebemos viram a mesma coisa para o resto do sistema.

Configuração mínima, em Configurações > Empresas:
  - token de homologação (e o de produção, quando for a hora)
  - regime tributário, inscrição estadual, número e bairro do endereço
  - CFOP padrão dentro do estado e para fora

Os defaults fiscais são de editora: livro é imune de ICMS (CST 41, ou CSOSN 400
no Simples) e tem PIS/COFINS com alíquota zero (CST 06). Quem vende outra coisa
troca no produto ou na linha.

Testes
------

97 testes, em arquivos que correspondem às camadas:

- ``tests/test_nfe_payload.py`` — a regra fiscal, sem banco: totais que fecham
  com a soma dos itens, arredondamento meio-para-cima (o ``round()`` do Python
  faz 1,005 virar 1,00 e a nota é rejeitada por um centavo), CSOSN no Simples
  contra CST no Normal, CPF contra CNPJ, interna contra interestadual, e o
  que ``missing_fields`` acusa antes de gastar uma chamada.
- ``tests/test_focus_client.py`` — o HTTP, com um ``requests`` falso: nada sai
  para a rede. Cobre a autenticação de senha vazia, o ``ref`` na query, e a
  tradução de 400/422/403/404 em exceção com a mensagem da Focus.
- ``tests/test_account_move_focus.py`` — o efeito no banco, em
  ``AccountTestInvoicingCommon``, sem dados de demonstração e sem mockar o ORM.
  Fatura vira payload, CFOP segue a UF, a chave de acesso só se grava quando a
  SEFAZ autoriza.
- ``tests/test_endereco_localizacao.py`` — a reconciliação com a localização
  brasileira da OCA. O módulo lê ``street_name``/``street_number``/``district``
  quando esses campos existem no registry e cai nos seus próprios quando não
  existem, sem depender da OCA no manifesto. Os dois caminhos são exercidos:
  o de banco sem ``l10n_br_base`` e o de banco com ele, cada teste pulando com
  a razão dita em voz alta quando está no banco errado. A consulta de CEP vai
  mockada — nenhum teste depende de rede.

Rodar::

    odoo -d <banco> -u liber_nfe_focus --test-enable \\
         --test-tags '/liber_nfe_focus' --stop-after-init

Fora do Odoo, ``scripts/focus_nfe_smoke.py`` emite uma nota de teste em
homologação usando este mesmo código de payload, para separar "o módulo está
errado" de "o cadastro na Focus está errado".
    """,
    'author': "EdLab Press",
    'category': 'Accounting',
    'version': '19.0.1.4.0',
    'license': 'AGPL-3',
    'depends': ['account', 'liber_nfe_xml'],
    'external_dependencies': {'python': ['requests', 'pytz']},
    'data': [
        'security/ir.model.access.csv',
        'data/focus_cron.xml',
        'data/nfe_cfop_oficial_data.xml',
        'data/nfe_operacao_data.xml',
        'views/nfe_operacao_views.xml',
        'views/res_company_views.xml',
        'views/res_partner_views.xml',
        'views/product_views.xml',
        'views/account_tax_views.xml',
        'views/account_fiscal_position_views.xml',
        'views/account_move_views.xml',
        'wizard/nfe_focus_cancel_wizard_views.xml',
        'wizard/nfe_focus_correcao_wizard_views.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'installable': True,
    'application': False,
}
