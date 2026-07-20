# -*- coding: utf-8 -*-
{
    'name': 'Bonus Copies',
    'version': '19.0.0.1.0',
    'summary': 'Comp copies for authors, press and influencers -- with quota, history and return',
    'description': """
Bonificações — exemplares dados a autores, jornalistas e influenciadores.

PROTÓTIPO. Ver NOTES.md (o quê e por quê), UX.md (como se usa) e TODO.md
(o que falta) na pasta do módulo.

A tese
======

Bonificação não gera receita, mas gera nota. Dar um livro não é "toma aí um
livro": é um ato com dono, motivo, custo e história. O módulo existe para que a
casa possa afirmar (com número) que às vezes dar um livro vale mais que pagar
mídia -- e para isso precisa das duas metades da conta: o **custo** e o
**retorno**.

O freio é orçamento, não permissão
==================================

A meta de doação aparece como contador vivo *enquanto se escolhe*, não como um
"não" na hora de salvar. Meta que só bloqueia no fim é punição, e faz a pessoa
parar de mandar livro -- que é tão ruim quanto mandar demais. O bloqueio duro
existe, mas é a rede, não o método.

Duas portas
===========

* **Contrato**: um botão. O contrato já decidiu; o trabalho é executar.
* **Marketing**: a tela de triagem (Bonificações > Enviar bonificação). Dezenas
  de pessoas e o trabalho *é* escolher. É o coração do módulo.

O que este protótipo NÃO faz
============================

* **Não gera o INV** (a nota de simples remessa). É a decisão D9, e ela passa pela
  contabilidade antes de virar código: no Odoo um ``out_invoice`` não consegue não
  ter recebível.

* Não emite XML (o repo é import-only).

* Não move estoque ainda (o tipo de operação ``BON/`` existe, mas ninguém o chama).

* Não toca consignação, evento, nem royalty.

Rodar ao vivo
=============

O banco ``bonus_demo`` tem o módulo instalado e o seed carregado::

    docker exec edlab19-odoo odoo -d bonus_demo -i liber_product_bonus \\
      --http-port=8072 --stop-after-init
    docker exec -i edlab19-odoo odoo shell -d bonus_demo --no-http \\
      < scripts/seed_bonus_demo.py
""",
    'author': 'EdLab Press',
    'category': 'Marketing',
    'depends': ['base', 'base_setup', 'mail', 'contacts', 'product', 'stock',
                'account', 'liber_nfe_xml', 'liber_nfe_remessa'],
    'data': [
        'security/product_bonus_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/bonus_reason_data.xml',
        'data/bonus_cron.xml',
        'wizard/bonus_list_combine_views.xml',
        'wizard/bonus_list_add_views.xml',
        'views/bonus_dispatch_views.xml',
        'views/account_move_views.xml',
        'views/bonus_views.xml',
        'views/bonus_reason_views.xml',
        'views/bonus_list_views.xml',
        'views/bonus_quota_views.xml',
        'views/partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/product_bonus_menus.xml',
        # Depois dos menus: este arquivo pendura um menuitem em
        # menu_bonus_root, que só existe a partir de product_bonus_menus.xml.
        # Numa base onde o módulo já estava instalado o menu pai já existia e o
        # erro não aparecia -- só numa instalação limpa.
        'wizard/bonus_list_import_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_product_bonus/static/src/scss/bonus_selection.scss',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
