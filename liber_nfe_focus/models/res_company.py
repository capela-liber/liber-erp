# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .focus_client import FocusClient, FocusError


class ResCompany(models.Model):
    _inherit = 'res.company'

    # -- credenciais ---------------------------------------------------
    # Os dois tokens convivem de propósito: trocar de ambiente é mudar UM
    # campo, não recolar credencial. Usar o token de homologação em produção
    # (ou o contrário) devolve 403, nunca uma nota errada.
    focus_ambiente = fields.Selection(
        selection=[('homologacao', 'Homologação'), ('producao', 'Produção')],
        string='Ambiente Focus NFe', default='homologacao', required=True,
        help="Homologação não tem validade fiscal e é onde se testa. "
             "Produção emite nota de verdade.")
    focus_token_homologacao = fields.Char(
        string='Token de Homologação', groups='base.group_system')
    focus_token_producao = fields.Char(
        string='Token de Produção', groups='base.group_system')
    focus_ref_prefix = fields.Char(
        string='Prefixo da Referência', default='EDLAB',
        help="Entra na referência única enviada à Focus. Bancos diferentes "
             "que usem o mesmo token (staging e produção, por exemplo) "
             "precisam de prefixos diferentes, senão uma consulta de um "
             "devolve a nota do outro.")

    # -- dados fiscais do emitente -------------------------------------
    focus_regime_tributario = fields.Selection(
        selection=[('1', 'Simples Nacional'),
                   ('2', 'Simples Nacional - excesso de sublimite'),
                   ('3', 'Regime Normal')],
        string='Regime Tributário', default='3', required=True,
        help="Decide se o campo de situação tributária do ICMS carrega CSOSN "
             "(Simples) ou CST (Normal). São tabelas diferentes.")

    # -- padrões da operação -------------------------------------------
    focus_natureza_operacao = fields.Char(
        string='Natureza da Operação (padrão)', default='Venda de mercadoria')
    focus_ncm_padrao = fields.Char(
        string='NCM padrão', default='49019900',
        help="Usado quando o produto não tem NCM próprio. 4901.99.00 é livro.")
    focus_codigo_beneficio_fiscal = fields.Char(
        string='Código de Benefício Fiscal (cBenef)', size=10,
        default='SP070130',
        help="São Paulo exige o cBenef desde abril de 2026 (Portaria SRE "
             "70/2025), e a imunidade do livro conta como benefício: sem ele a "
             "SEFAZ devolve a rejeição 930. SP070130 é 'não incidência - livro, "
             "jornal ou periódico' (art. 7º, XIII do RICMS), e vale para o CST "
             "41. Estados que não exigem cBenef: deixe vazio.")
    focus_ibs_cbs_cst = fields.Char(
        string='CST do IBS/CBS', size=3, default='410',
        help="Reforma tributária: a SEFAZ passou a exigir o grupo IBS/CBS em "
             "30/07/2026. 410 é 'Imunidade e não incidência', que é o do livro.")
    focus_ibs_cbs_classificacao = fields.Char(
        string='Classificação Tributária (cClassTrib)', size=6, default='410008',
        help="Anda junto com o CST e tem de ser compatível com ele. 410008 é "
             "'Fornecimentos de livros, jornais, periódicos e do papel "
             "destinado a sua impressão'.")
    focus_codigo_produto = fields.Selection(
        selection=[('barras', 'Código de barras (ISBN)'),
                   ('interno', 'Referência interna')],
        string='Código do produto na nota', default='barras', required=True,
        help="O que vai no campo cProd. Para editora o natural é o ISBN: é o "
             "identificador que a livraria concilia. A referência interna serve "
             "a quem tem código próprio e o cliente conhece.")
    focus_forma_pagamento_vista = fields.Selection(
        selection=[('01', '01 - Dinheiro'), ('03', '03 - Cartão de crédito'),
                   ('04', '04 - Cartão de débito'), ('15', '15 - Boleto bancário'),
                   ('17', '17 - PIX'), ('99', '99 - Outros')],
        string='Forma de pagamento à vista', default='01',
        help="Usada quando a venda não tem parcela a vencer. Venda a prazo sai "
             "sempre como duplicata mercantil (14), que é o que a duplicata é.")
    focus_operacao_padrao_id = fields.Many2one(
        'nfe.operacao', string='Operação padrão',
        help="A operação usada quando nada mais a define. Um só campo: o CFOP "
             "completo nasce dela mais o destino — 5xxx dentro do estado, "
             "6xxx para fora.")

    def _focus_token(self):
        """Token do ambiente selecionado. Explode com mensagem útil se faltar."""
        self.ensure_one()
        # sudo() porque os campos são group_system e quem emite nota é do
        # financeiro, não administrador do sistema.
        company = self.sudo()
        token = (company.focus_token_producao
                 if company.focus_ambiente == 'producao'
                 else company.focus_token_homologacao)
        if not token:
            raise UserError(_(
                "A empresa %(empresa)s não tem token da Focus NFe para o "
                "ambiente %(ambiente)s. Configure em Configurações > Empresas.",
                empresa=self.display_name, ambiente=company.focus_ambiente))
        return token

    def _focus_client(self):
        self.ensure_one()
        return FocusClient(self._focus_token(), ambiente=self.sudo().focus_ambiente)

    def _focus_emitente_data(self):
        """Dicionário do emitente no formato de `nfe_payload.build_payload`."""
        self.ensure_one()
        partner = self.partner_id
        if not self.vat:
            raise UserError(_(
                "A empresa %s não tem CNPJ (campo CPF/CNPJ) preenchido.",
                self.display_name))
        # O endereço do emitente sai do parceiro da empresa, e é lá que a
        # localização brasileira (quando instalada) guarda número e bairro.
        endereco = partner._nfe_endereco()
        return {
            'cnpj': self.vat,
            'nome': self.name,
            'nome_fantasia': partner.name,
            'logradouro': endereco['logradouro'],
            'numero': endereco['numero'],
            'complemento': partner.street2,
            'bairro': endereco['bairro'],
            'municipio': endereco['municipio'],
            'uf': partner.state_id.code,
            'cep': partner.zip,
            'telefone': partner.phone,
            'inscricao_estadual': endereco['inscricao_estadual'],
            'regime_tributario': int(self.focus_regime_tributario or '3'),
        }

    def action_focus_gerar_impostos(self):
        """Cria um imposto por CFOP configurado, que é como a posição fiscal
        entrega o CFOP à nota.

        Gera a partir da tabela de CFOPs do módulo — **não** do legado. É a
        diferença entre configuração que se refaz a cada migração e configuração
        que se reproduz por um botão: o legado serviu para descobrir o formato,
        e agora ele não é mais necessário.

        Alíquota zero: o imposto existe para marcar a operação, não para
        tributar. O livro é imune, e ainda assim a nota precisa dizer qual é a
        operação.

        Idempotente: rodar de novo não duplica, só liga o CFOP ao que faltava.
        """
        self.ensure_one()
        Tax = self.env['account.tax']
        operacoes = self.env['nfe.operacao'].search([], order='sentido, code')
        criados = ligados = 0
        # No Simples o campo carrega CSOSN (400), no regime normal CST (41).
        # O nome segue o do legado -- "ICMS 41 - CFOP 5101 - EDLAB" -- porque é
        # como a casa reconhece esses impostos há três anos.
        cst = '400' if self.focus_regime_tributario == '1' else '41'
        for operacao in operacoes:
            # O nome guarda o SUFIXO, não um CFOP inteiro: o imposto vale para
            # dentro e para fora do estado, e o primeiro dígito só existe na
            # nota. Um imposto por operação, não dois.
            nome = 'ICMS %s - OP %s%s - %s' % (
                cst, 'e' if operacao.sentido == 'entrada' else 'x',
                operacao.code, (self.name or '')[:20].strip())
            imposto = Tax.search([
                ('name', '=', nome), ('company_id', '=', self.id)], limit=1)
            if imposto:
                if not imposto.nfe_operacao_id:
                    imposto.nfe_operacao_id = operacao
                    ligados += 1
                continue
            Tax.create({
                'name': nome,
                'amount': 0.0,
                'amount_type': 'percent',
                'type_tax_use': 'sale',
                'company_id': self.id,
                'nfe_operacao_id': operacao.id,
            })
            criados += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Impostos fiscais gerados"),
                'message': _(
                    "%(criados)s criados, %(ligados)s completados, sobre "
                    "%(total)s operações.",
                    criados=criados, ligados=ligados, total=len(operacoes)),
                'sticky': False,
            },
        }

    def action_focus_testar_conexao(self):
        """Confere token e ambiente sem emitir nada."""
        self.ensure_one()
        try:
            empresas = self._focus_client().testar_conexao()
        except FocusError as exc:
            raise UserError(_("Focus NFe: %s", exc.message)) from exc
        ambiente = self.sudo().focus_ambiente
        # A lista de emitentes só vem com token de conta. Com token de
        # emitente ela vem vazia, e isso não é defeito nenhum -- então a
        # mensagem não pode anunciar "0 emitentes" como se fosse resultado.
        if empresas:
            mensagem = _(
                "Ambiente %(ambiente)s, %(n)s emitente(s) no cadastro.",
                ambiente=ambiente, n=len(empresas))
        else:
            mensagem = _("Ambiente %(ambiente)s, token aceito.",
                         ambiente=ambiente)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Focus NFe conectada"),
                'message': mensagem,
                'sticky': False,
            },
        }

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Empresa brasileira nova já nasce com as posições fiscais da casa.

        Sem isto, criar a quinta editora significa lembrar de rodar a semeadura
        à mão -- e a hora de descobrir que ninguém lembrou é a primeira nota,
        que sai com a posição em branco.
        """
        companies = super().create(vals_list)
        brasileiras = companies.filtered(
            lambda c: c.partner_id.country_id.code == 'BR')
        if brasileiras:
            self.env['account.fiscal.position']._nfe_semear_posicoes(
                companies=brasileiras)
        return companies
