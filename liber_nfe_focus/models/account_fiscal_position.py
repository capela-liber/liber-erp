# -*- coding: utf-8 -*-
"""A operação fiscal na posição fiscal — a ligação direta, e a que se vê.

A posição fiscal SEMPRE decidiu a operação; ela só o fazia por um caminho
indireto, pelo imposto que substituía. Isso funciona (é o que o sistema em
produção faz em 110 mil linhas) mas obriga a abrir o imposto para descobrir que
CFOP vai sair, e a confiar que ninguém trocou o imposto no meio.

Aqui a posição fiscal diz a operação em voz alta. O caminho pelo imposto
continua valendo, e continua ganhando quando existe: ele é POR LINHA, e uma nota
pode misturar operações -- consignação e bonificação na mesma remessa. A posição
fiscal é do cabeçalho, e cabeçalho não desempata linha.

As posições nascem prontas
--------------------------

Cada operação da casa vira uma posição fiscal por empresa, criada pelo módulo,
com o nome no formato da casa e a operação **já ligada**. Antes disso a ligação
era trabalho manual: as posições vieram do legado sem operação nenhuma, e
apontar catorze operações em cinco empresas à mão, uma vez por banco, é setenta
oportunidades de errar em silêncio -- e errar aqui é emitir a nota com o CFOP
do vizinho.

A semeadura é idempotente e conservadora: identifica a posição pelo par
(empresa, operação) e não cria a segunda. Quem já tem a sua -- adotada do legado
pela migração 19.0.1.5.0 -- não ganha uma cópia.
"""

import logging
import re

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# O que sai do nome herdado do legado. O nome da empresa era o que gerava as
# catorze redações do 5101; o "CFOP: 5101/6101" no fim volta depois, num formato
# só; o asterisco não quer dizer nada que alguém saiba dizer hoje.
#
# A letra NÃO sai: é ela que estamos preservando. O "PF"/"PJ" também não -- é a
# única coisa que distingue duas posições da mesma empresa com o mesmo CFOP.
LIXO_NO_NOME = [
    re.compile(r'\s*\(([^)]*(?:edições|edicoes|Press|Hedra|Edlab|EdLab|'
               r'N-1|n-1|saíra|saira|Kalinka|Circuito|Plana)[^)]*)\)', re.I),
    re.compile(r'\s*CFOP[:\s]*[\d/\s]+$', re.I),
    re.compile(r'\s*\*+\s*'),
]
CFOP_NO_NOME = re.compile(r'\b([1256])(\d{3})\b')
# A letra no começo do nome herdado. Sai para voltar: quem manda é a da operação.
LETRA_NO_NOME = re.compile(r'^\(([A-Z])\)\s*')
SENTIDO_DO_DIGITO = {'1': 'entrada', '2': 'entrada', '5': 'saida', '6': 'saida'}


class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'

    nfe_operacao_id = fields.Many2one(
        'nfe.operacao', string='Operação fiscal',
        help="A operação que esta posição fiscal representa. O CFOP completo "
             "nasce dela mais o endereço do cliente — 5xxx dentro do estado, "
             "6xxx para fora.\n\n"
             "Um imposto que carregue operação própria ganha desta, porque o "
             "imposto é por linha e a posição fiscal é da nota inteira.")
    nfe_cfop_interno_id = fields.Many2one(
        'nfe.cfop', string='CFOP dentro do estado',
        compute='_compute_nfe_cfops', help="Só leitura: sai da operação.")
    nfe_cfop_externo_id = fields.Many2one(
        'nfe.cfop', string='CFOP para outro estado',
        compute='_compute_nfe_cfops', help="Só leitura: sai da operação.")

    @api.depends('nfe_operacao_id')
    def _compute_nfe_cfops(self):
        for posicao in self:
            operacao = posicao.nfe_operacao_id
            posicao.nfe_cfop_interno_id = operacao.cfop_record('interna')
            posicao.nfe_cfop_externo_id = operacao.cfop_record('interestadual')

    # ------------------------------------------------------- semeadura
    @api.model
    def _nfe_empresas_brasileiras(self):
        """Quem recebe as posições: só quem emite NFe.

        O critério é o país da empresa, não o CNPJ -- a EdLab Participações é
        brasileira e está sem CNPJ preenchido, e uma posição fiscal a mais não
        faz mal a ninguém, enquanto semear a `My Company` americana faz.
        """
        return self.env['res.company'].sudo().search([
            ('partner_id.country_id.code', '=', 'BR')])

    @api.model
    def _nfe_semear_posicoes(self, companies=None, operacoes=None):
        """Uma posição fiscal por (empresa, operação), com a operação ligada.

        Devolve as posições criadas. Não toca nas que já existem: a chave é o
        par (empresa, operação), então rodar duas vezes não duplica, e a posição
        que a migração adotou do legado ocupa o lugar da que nasceria aqui.
        """
        if companies is None:
            companies = self._nfe_empresas_brasileiras()
        if operacoes is None:
            operacoes = self.env['nfe.operacao'].sudo().search([])
        if not companies or not operacoes:
            return self.browse()

        ja_existem = self.sudo().with_context(active_test=False).search([
            ('company_id', 'in', companies.ids),
            ('nfe_operacao_id', 'in', operacoes.ids)])
        ocupados = {(p.company_id.id, p.nfe_operacao_id.id) for p in ja_existem}

        valores = []
        for company in companies:
            for operacao in operacoes:
                if (company.id, operacao.id) in ocupados:
                    continue
                valores.append({
                    'name': operacao.nome_posicao_fiscal(),
                    'company_id': company.id,
                    'nfe_operacao_id': operacao.id,
                })
        if not valores:
            return self.browse()
        criadas = self.sudo().create(valores)
        _logger.info("liber_nfe_focus: %d posições fiscais criadas em %d "
                     "empresas", len(criadas), len(companies))
        return criadas

    # --------------------------------------------------------- adoção
    @api.model
    def _nfe_operacao_do_nome(self, nome):
        """A operação que o nome herdado do legado declara, ou vazio.

        O legado escrevia o CFOP no próprio nome -- "CFOP: 5917/6917" -- porque
        não tinha onde mais guardá-lo. É essa a pista: o primeiro código de
        quatro dígitos diz o sentido (1/2 entrada, 5/6 saída) e o sufixo.

        Nem todo nome mapeia, e está certo que não mapeie. "(C) Devolução
        simbólica de terceiros CFOP: 1917" pede uma entrada 917 que não existe
        na tabela da casa -- a mesma operação que a n-1 emitiu 18 vezes como
        saída 5919. Nome que não mapeia fica como está, e aparece no relatório.
        """
        achado = CFOP_NO_NOME.search(nome or '')
        if not achado:
            return self.env['nfe.operacao']
        primeiro, sufixo = achado.group(1), achado.group(2)
        return self.env['nfe.operacao'].sudo().search([
            ('code', '=', sufixo),
            ('sentido', '=', SENTIDO_DO_DIGITO[primeiro]),
        ], limit=1)

    @api.model
    def _nfe_nome_limpo(self, nome, operacao):
        """O nome herdado, no formato da casa: letra, o que é, e o par de CFOPs.

        A letra que vem no nome é **descartada** e reposta pela da operação. Não
        é preciosismo: o legado discordava de si mesmo sobre a feira, que saiu
        como "(E) Remessa para feiras e eventos" e como "(Z) Remessa de
        mercadoria ou bem para exposição ou feira", as duas em 5914/6914. Uma
        taxonomia em que a mesma operação tem duas letras não é taxonomia. A
        letra passa a morar num lugar só -- na operação -- e o nome a repete.
        """
        limpo = nome or ''
        for padrao in LIXO_NO_NOME:
            limpo = padrao.sub(' ', limpo)
        limpo = LETRA_NO_NOME.sub('', limpo.lstrip())
        limpo = ' '.join(limpo.split()).strip(' -–—')
        if not limpo:
            return operacao.nome_posicao_fiscal()
        if operacao.letra:
            limpo = '(%s) %s' % (operacao.letra, limpo)
        interno = operacao.cfop_para('interna')
        externo = operacao.cfop_para('interestadual')
        if interno and externo:
            return '%s — %s/%s' % (limpo, interno, externo)
        return limpo

    @api.model
    def _nfe_adotar_posicoes_do_legado(self, renomear=True):
        """Liga as posições herdadas à sua operação, e arruma o nome.

        Só mexe em posição **sem** operação: quem já foi ligado, à mão ou pela
        semeadura, fica como está.

        O nome só muda se o nome novo não colidir com outro da mesma empresa.
        A Hedra tem "(A) Venda de Produção PJ" e "(A) Vendas de Produção PF",
        as duas em 5101/6101: limpar as duas até o osso faria duas posições com
        o mesmo nome, e escolher entre elas na fatura viraria adivinhação. Em
        caso de colisão, mapeia e deixa o nome velho.

        Devolve (adotadas, renomeadas, sem_operacao) para o relatório.
        """
        candidatas = self.sudo().with_context(active_test=False).search([
            ('nfe_operacao_id', '=', False)])
        adotadas = self.browse()
        renomeadas = self.browse()
        sem_operacao = self.browse()

        # Os nomes já em uso por empresa, para não criar duas iguais.
        usados = {}
        for posicao in self.sudo().with_context(active_test=False).search([]):
            usados.setdefault(posicao.company_id.id, set()).add(posicao.name)

        for posicao in candidatas:
            operacao = self._nfe_operacao_do_nome(posicao.name)
            if not operacao:
                sem_operacao |= posicao
                continue
            posicao.nfe_operacao_id = operacao
            adotadas |= posicao
            if not renomear:
                continue
            novo = self._nfe_nome_limpo(posicao.name, operacao)
            da_empresa = usados.setdefault(posicao.company_id.id, set())
            if novo == posicao.name or novo in da_empresa:
                continue
            da_empresa.discard(posicao.name)
            da_empresa.add(novo)
            _logger.info("liber_nfe_focus: posição fiscal %r -> %r",
                         posicao.name, novo)
            posicao.name = novo
            renomeadas |= posicao

        _logger.info("liber_nfe_focus: %d posições adotadas, %d renomeadas, "
                     "%d sem operação dedutível do nome",
                     len(adotadas), len(renomeadas), len(sem_operacao))
        return adotadas, renomeadas, sem_operacao
