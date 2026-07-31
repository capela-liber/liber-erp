# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# "Rua das Acácias, 123" -> ("Rua das Acácias", "123")
#
# A vírgula é exigida de propósito. Sem ela, "Rodovia Anhanguera km 12" viraria
# número 12 e a nota sairia com endereço errado -- e endereço errado na NFe é
# problema fiscal. 'S/N' num logradouro que tem número é visivelmente estranho e
# alguém corrige; um número inventado passa despercebido.
NUMERO_NO_FIM = re.compile(r'^(.*?),\s*(\d+[A-Za-z]?)$')

# Os campos de endereço que podem ou não existir, conforme quem está instalado:
#
#   street, street2       sempre (base)
#   street_name, street_number   base_address_extended, do core
#   district              l10n_br_base, da OCA
#   l10n_br_ie_code       l10n_br_base, da OCA
#   nfe_numero, nfe_bairro, nfe_inscricao_estadual   deste módulo, sempre
#
# Este módulo não depende de nenhuma localização: quem quer emitir nota não
# deve ser obrigado a instalar a localização inteira. Mas quando ela está
# instalada, é ela que manda -- ler o campo próprio nesse caso seria ler o
# palpite de volta e ignorar o que o usuário digitou no formulário de verdade.
CAMPOS_ENDERECO = (
    'street', 'street_name', 'street_number', 'district',
    'nfe_numero', 'nfe_bairro',
    'l10n_br_ie_code', 'nfe_inscricao_estadual',
)


def endereco_para_nfe(campos):
    """Escolhe a fonte de cada pedaço do endereço. Entra dicionário, sai dicionário.

    `campos` traz **só** os campos que existem no registry do parceiro, com o
    valor de cada um. Um campo ausente e um campo vazio dão no mesmo aqui, de
    propósito: o que interessa é a ordem de precedência.

    No endereço a localização vem primeiro, porque quando ela está instalada o
    formulário de endereço é o dela: `_view_get_address` troca o bloco inteiro
    pelo layout brasileiro e os campos deste módulo somem da tela. Ler o campo
    próprio nesse caso seria ignorar o que o usuário digitou.

    - logradouro: `street_name` antes de `street`. Com `base_address_extended`,
      `street` deixa de ser o logradouro e passa a ser derivado
      ("Rua das Acácias, 123"); mandar isso como logradouro repetiria o
      número dentro do endereço.
    - número: `street_number` antes de `nfe_numero`.
    - bairro: `district` antes de `nfe_bairro`.

    A inscrição estadual inverte a ordem, e por isso mesmo: ela não fica no
    bloco de endereço, então `nfe_inscricao_estadual` continua visível e
    editável ao lado do `l10n_br_ie_code` da OCA. Quem digitou no campo deste
    módulo digitou onde a configuração do módulo mandou; o da localização
    entra só quando o nosso está vazio.

    Sem a localização, o número sai do logradouro pela mesma regra que já
    alimentava o `nfe_numero`: "Rua X, 123" manda "Rua X" e "123". Antes o
    logradouro ia inteiro e o número aparecia duas vezes na nota. Assim o mesmo
    parceiro gera o mesmo endereço com ou sem localização instalada, que é o
    ponto de reconciliar os campos.

    A vírgula no fim do logradouro é aparada porque o `street_split` do core
    quebra "Rua X, 123" em ("Rua X,", "123") e devolve a vírgula grudada.
    """
    if campos.get('street_name'):
        logradouro = campos['street_name']
    else:
        logradouro = (campos.get('street') or '').strip()
        casado = NUMERO_NO_FIM.match(logradouro)
        if casado:
            logradouro = casado.group(1)
    logradouro = logradouro.strip().rstrip(',').strip()
    return {
        'logradouro': logradouro,
        # 'S/N' é o que a SEFAZ espera de endereço sem número. Nunca vazio.
        'numero': campos.get('street_number') or campos.get('nfe_numero') or 'S/N',
        'bairro': campos.get('district') or campos.get('nfe_bairro') or '',
        'inscricao_estadual': (campos.get('nfe_inscricao_estadual')
                               or campos.get('l10n_br_ie_code') or ''),
    }


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # O Odoo de fábrica não tem número nem bairro: o endereço brasileiro cabe
    # mal em street/street2. A SEFAZ exige os dois separados, então eles moram
    # aqui -- e só valem enquanto ninguém instalar a localização, que traz
    # street_number (base_address_extended) e district (l10n_br_base). Ver
    # `endereco_para_nfe`.
    nfe_numero = fields.Char(
        string='Número', size=60,
        compute='_compute_nfe_numero', store=True, readonly=False,
        help="Número do endereço, exigido separado pela SEFAZ. Preenchido "
             "automaticamente a partir do fim do logradouro quando dá; "
             "'S/N' quando não há número. Com a localização brasileira "
             "instalada, quem manda é o campo 'Número' do endereço.")
    nfe_bairro = fields.Char(
        string='Bairro', size=60,
        help="Com a localização brasileira instalada, quem manda é o campo "
             "'Bairro' do endereço.")
    nfe_inscricao_estadual = fields.Char(
        string='Inscrição Estadual', size=14,
        help="Somente dígitos. Vazio significa não contribuinte ou isento — "
             "veja o indicador ao lado.")
    nfe_indicador_ie = fields.Selection(
        selection=[('1', 'Contribuinte de ICMS'),
                   ('2', 'Isento de inscrição'),
                   ('9', 'Não contribuinte')],
        string='Indicador de IE',
        help="Deixe vazio para deduzir: com IE preenchida é contribuinte; "
             "pessoa física é não contribuinte; o resto é isento.")

    @api.depends('street')
    def _compute_nfe_numero(self):
        """Tenta ler o número do fim do logradouro.

        É palpite, e por isso o campo é editável (`readonly=False`): endereço
        sem número no fim vira 'S/N', que é o que a SEFAZ espera nesse caso.
        """
        for partner in self:
            if partner.nfe_numero:
                continue
            match = NUMERO_NO_FIM.match((partner.street or '').strip())
            partner.nfe_numero = match.group(2) if match else 'S/N'

    @api.constrains('nfe_inscricao_estadual')
    def _check_nfe_inscricao_estadual(self):
        for partner in self:
            ie = partner.nfe_inscricao_estadual
            if ie and not re.fullmatch(r'[\d.\-/\s]+', ie):
                raise ValidationError(_(
                    "A Inscrição Estadual de %(nome)s deve conter apenas "
                    "dígitos (recebido %(ie)r).",
                    nome=partner.display_name, ie=ie))

    def _nfe_endereco(self):
        """Endereço do parceiro já resolvido entre localização e campos próprios.

        A leitura é defensiva por construção: só entra em `campos` o que
        existe no registry, do mesmo jeito que este módulo já faz com
        `sale.order.cfop_id` e `product.template.metabooks_ncm`. Sem a
        localização instalada, o dicionário chega menor e a função pura cai
        nos campos deste módulo sozinha.
        """
        self.ensure_one()
        campos = {nome: self[nome]
                  for nome in CAMPOS_ENDERECO if nome in self._fields}
        endereco = endereco_para_nfe(campos)
        # `city` é texto livre; com l10n_br_base o município de verdade é o
        # city_id, e o texto só acompanha por onchange -- que não roda em
        # create() programático. Sem o fallback a nota sai sem município.
        municipio = self.city
        if not municipio and 'city_id' in self._fields:
            municipio = self.city_id.name
        endereco['municipio'] = municipio or ''
        return endereco

    def _focus_destinatario_data(self):
        """Dicionário do destinatário no formato do `nfe_payload`."""
        self.ensure_one()
        documento = re.sub(r'\D', '', self.vat or '')
        indicador = int(self.nfe_indicador_ie) if self.nfe_indicador_ie else None
        endereco = self._nfe_endereco()
        return {
            'nome': self.name,
            'cnpj': documento if len(documento) == 14 else None,
            'cpf': documento if len(documento) == 11 else None,
            'inscricao_estadual': endereco['inscricao_estadual'],
            'indicador_ie': indicador,
            'logradouro': endereco['logradouro'],
            'numero': endereco['numero'],
            'complemento': self.street2,
            'bairro': endereco['bairro'],
            'municipio': endereco['municipio'],
            'uf': self.state_id.code,
            'cep': self.zip,
            'telefone': self.phone,
            'email': self.email,
            'pais': self.country_id.name,
        }
