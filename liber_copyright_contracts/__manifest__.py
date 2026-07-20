# -*- coding: utf-8 -*-
{
    'name': 'Copyright Contracts',
    'version': '19.0.1.0.0',
    'summary': 'Copyright contract management (beneficiaries, works and tiered royalties)',
    'description': """
Copyright contract management for a publishing house.

Links beneficiaries (authors, translators, illustrators) to works (products),
recording the royalty percentage per copies tier and the recoupable /
non-recoupable advances. This version only records the contract terms
(it does not compute royalties from sales).

Testes
======

O módulo traz um *tour* de regressão que dirige a interface do início ao fim:
cria um contrato, confere o prazo de renovação sugerido pelas datas, adiciona
uma linha de royalty (beneficiário x obra) com duas faixas de cópias e um
adiantamento recuperável, salva, valida, renova, reatribui o responsável pelo
menu Ação e cancela. Se qualquer passo quebrar, é uma regressão.

Rodar ao vivo (para ver na tela)
--------------------------------

1. Entre no banco ``copyright19`` (é onde o módulo está instalado).
2. Ative o modo desenvolvedor.
3. No console do navegador, execute::

     odoo.startTour("copyright_contracts_tour")

O Odoo executa cada passo sozinho. Não precisa de nada além do navegador.

Rodar automatizado (headless / CI)
----------------------------------

::

    odoo -d copyright19 -u liber_copyright_contracts \\
      --test-enable --test-tags '/liber_copyright_contracts:TestCopyrightContractsTour' \\
      --http-port=8072 --stop-after-init

Pré-requisitos do modo headless: o pacote Python ``websocket-client`` e um
binário real do Google Chrome/Chromium (a imagem ``odoo:19`` não os traz), além
de uma porta HTTP livre.
""",
    'author': 'EdLab Press',
    'category': 'Sales/Contracts',
    'depends': ['base', 'base_setup', 'mail', 'contacts', 'product'],
    'data': [
        'security/contracts_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/ir_cron.xml',
        'views/contract_views.xml',
        'views/contract_reassign_views.xml',
        'views/partner_views.xml',
        'views/product_views.xml',
        'views/contract_menus.xml',
        'views/res_config_settings_views.xml',
    ],
    'demo': [
        'demo/contracts_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_copyright_contracts/static/src/js/copyright_contracts_tour.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
