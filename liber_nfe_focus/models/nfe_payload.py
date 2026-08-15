# -*- coding: utf-8 -*-
"""Monta o JSON da NFe modelo 55 no formato da Focus NFe.

Também sem Odoo: entra dicionário, sai dicionário. É aqui que mora a regra
fiscal (CST/CSOSN, imunidade do livro, local de destino), e é a parte que mais
vai mudar -- por isso ela é testável sem subir banco nenhum.

Os nomes dos campos são os da Focus, não os do XML da SEFAZ: `cnpj_emitente`,
`icms_situacao_tributaria`, `items[].codigo_ncm`. A referência completa está em
https://campos.focusnfe.com.br/nfe/NotaFiscalXML.html
"""

import re
from decimal import Decimal, ROUND_HALF_UP

# ----------------------------------------------------------------------
# tabelas
# ----------------------------------------------------------------------

# tipo_documento
ENTRADA, SAIDA = 0, 1

# finalidade_emissao
FINALIDADE_NORMAL = 1
FINALIDADE_COMPLEMENTAR = 2
FINALIDADE_AJUSTE = 3
FINALIDADE_DEVOLUCAO = 4

# local_destino
DESTINO_INTERNA = 1
DESTINO_INTERESTADUAL = 2
DESTINO_EXTERIOR = 3

# presenca_comprador
PRESENCA_NAO_SE_APLICA = 0
PRESENCA_PRESENCIAL = 1
PRESENCA_INTERNET = 2
PRESENCA_TELEATENDIMENTO = 3
PRESENCA_ENTREGA_DOMICILIO = 4
PRESENCA_PRESENCIAL_FORA = 5
PRESENCA_OUTROS = 9

# modalidade_frete
FRETE_EMITENTE = 0
FRETE_DESTINATARIO = 1
FRETE_TERCEIROS = 2
FRETE_PROPRIO_EMITENTE = 3
FRETE_PROPRIO_DESTINATARIO = 4
FRETE_SEM = 9

# indicador_inscricao_estadual_destinatario
IE_CONTRIBUINTE = 1
IE_ISENTO = 2
IE_NAO_CONTRIBUINTE = 9

# regime_tributario (CRT)
CRT_SIMPLES = 1
CRT_SIMPLES_EXCESSO = 2
CRT_NORMAL = 3

# O livro é imune de ICMS (CF art. 150, VI, "d") e tem PIS/COFINS com alíquota
# zero (Lei 10.865/2004, art. 28, VI). Daí os defaults abaixo, que valem para
# uma editora e não valem para todo mundo -- por isso são configuráveis.
CST_ICMS_NAO_TRIBUTADA = '41'
CSOSN_SIMPLES_IMUNE = '400'
CST_PIS_COFINS_ALIQUOTA_ZERO = '06'

# São Paulo exige o código de benefício fiscal (cBenef) desde abril de 2026
# (Portaria SRE 70/2025). Sem ele a SEFAZ devolve a rejeição 930, "CST com
# benefício fiscal e não informado o código de benefício fiscal" -- e a
# imunidade do livro conta como benefício.
#
# SP070130 = "Não incidência - operação ou prestação que envolver livro, jornal
# ou periódico ou o papel destinado à sua impressão" (art. 7º, XIII do RICMS).
# Na tabela da SEFAZ-SP ele vale para o CST 41 e também para o Simples.
CBENEF_SP_LIVRO = 'SP070130'

# Reforma tributária (IBS/CBS). A SEFAZ-SP passou a EXIGIR o grupo em
# 30/07/2026 -- o mesmo payload autorizado duas horas antes passou a devolver
# "Rejeição 1115: IBS/CBS não informado".
#
# Os valores abaixo não são palpite: são os que o sistema em produção emite em
# 17.282 linhas. CST 410 é "Imunidade e não incidência"; a classificação 410008
# é "Fornecimentos de livros, jornais, periódicos e do papel destinado a sua
# impressão". Livro tem imunidade constitucional que a reforma preservou.
CST_IBS_CBS_IMUNE = '410'
CLASS_TRIB_LIVRO = '410008'
CST_IBS_CBS_TRIBUTADO = '000'
CLASS_TRIB_TRIBUTADO = '000001'

# Formas de pagamento (tPag). A Focus assume 01 (dinheiro) quando nada se diz --
# e livro vendido para livraria não se paga em dinheiro no balcão.
FORMA_DINHEIRO = '01'
FORMA_DUPLICATA = '14'      # duplicata mercantil: a venda a prazo da casa
FORMA_SEM_PAGAMENTO = '90'  # remessa, consignação, bonificação: nada se paga

# Em homologação a SEFAZ EXIGE esta razão social no destinatário -- é regra
# dela, não da Focus. Nota de teste com nome de cliente real é rejeitada. Sem
# isto, ninguém consegue testar a partir do Odoo sem renomear os clientes.
NOME_DESTINATARIO_HOMOLOGACAO = (
    'NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL')

# Só estes CSTs aceitam cBenef. Mandar o código junto de um CST tributado
# (00, 20 com redução etc.) é rejeição por campo indevido, o espelho do 930.
CST_QUE_PEDEM_CBENEF = frozenset(
    ('20', '30', '40', '41', '50', '51', '53', '70', '90'))

CAMPOS_OBRIGATORIOS_NOTA = (
    'natureza_operacao', 'data_emissao', 'tipo_documento', 'finalidade_emissao',
    'cnpj_emitente', 'nome_emitente', 'logradouro_emitente', 'numero_emitente',
    'bairro_emitente', 'municipio_emitente', 'uf_emitente', 'cep_emitente',
    'inscricao_estadual_emitente', 'regime_tributario',
    'nome_destinatario', 'logradouro_destinatario', 'numero_destinatario',
    'bairro_destinatario', 'municipio_destinatario', 'uf_destinatario',
)

CAMPOS_OBRIGATORIOS_ITEM = (
    'numero_item', 'codigo_produto', 'descricao', 'codigo_ncm', 'cfop',
    'unidade_comercial', 'quantidade_comercial', 'valor_unitario_comercial',
    'icms_origem', 'icms_situacao_tributaria',
    'pis_situacao_tributaria', 'cofins_situacao_tributaria',
)


# ----------------------------------------------------------------------
# normalização
# ----------------------------------------------------------------------

def only_digits(value):
    """CNPJ, CPF, CEP e telefone vão sem pontuação; `None` continua `None`."""
    if value is None:
        return None
    return re.sub(r'\D', '', str(value)) or None


def money(value, casas=2):
    """Arredonda meio-para-cima, como a SEFAZ, e devolve string.

    Float aqui é armadilha: 1.005 vira 1.00 no `round()` do Python e a soma dos
    itens deixa de bater com o total da nota, que é rejeição na hora.
    """
    if value in (None, ''):
        return None
    quant = Decimal(1).scaleb(-casas)
    return str(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def abater_excesso(itens, chave, total):
    """Impede que a cobrança passe o total da nota, abatendo do fim.

    São dois arredondamentos do mesmo dinheiro. A NFe soma os itens JÁ
    arredondados -- é o que a SEFAZ confere. O Odoo, com a empresa arredondando
    "globalmente" (`round_globally`, que é como as seis da casa estão), soma os
    valores exatos das linhas, arredonda no fim, e joga a sobra na conta de uma
    das linhas para o lançamento fechar. Meio centavo por linha vira um centavo
    no rodapé, e a cobrança sai maior que a nota que ela cobra.

    O abatimento começa pela ÚLTIMA parcela, que é onde o comércio sempre pôs a
    sobra de arredondamento: as primeiras são redondas e a última fecha a conta.

    SÓ SE TIRA, NUNCA SE PÕE. Cobrar menos que o total é legítimo e acontece
    todo dia: a remessa em consignação sai com a forma 90 e valor zero contra
    uma nota de valor cheio, e a fatura que se paga metade à vista manda só a
    parcela que vence depois. Completar essas duas seria inventar cobrança.
    """
    itens = [dict(i) for i in itens]
    excesso = (sum(Decimal(i.get(chave) or 0) for i in itens)
               - Decimal(money(total) or '0'))
    if excesso <= 0:
        return itens
    for item in reversed(itens):
        valor = Decimal(item.get(chave) or 0)
        abate = min(valor, excesso)
        item[chave] = money(valor - abate)
        excesso -= abate
        if excesso <= 0:
            break
    return itens


def texto(value, limite):
    """Corta no limite da SEFAZ e tira espaço duplicado."""
    if not value:
        return None
    limpo = ' '.join(str(value).split())
    return limpo[:limite] or None


def local_destino(uf_emitente, uf_destinatario):
    """1 interna, 2 interestadual, 3 exterior -- a SEFAZ confere contra as UFs."""
    origem = (uf_emitente or '').strip().upper()
    destino = (uf_destinatario or '').strip().upper()
    if destino in ('EX', 'EXTERIOR', ''):
        return DESTINO_EXTERIOR if destino else DESTINO_INTERNA
    return DESTINO_INTERNA if origem == destino else DESTINO_INTERESTADUAL


def tipo_documento_por_cfop(codigo):
    """O primeiro dígito do CFOP diz o sentido da mercadoria.

    1, 2 e 3 são entradas (vem para nós); 5, 6 e 7 são saídas. Uma devolução de
    consignação (1918) é entrada mesmo quando somos nós que emitimos a nota --
    e sair como saída inverte o sentido da operação para a SEFAZ.

    Devolve None quando o CFOP não diz nada, para quem chama decidir.
    """
    digitos = only_digits(codigo)
    if not digitos:
        return None
    if digitos[0] in '123':
        return ENTRADA
    if digitos[0] in '567':
        return SAIDA
    return None


# O primeiro dígito do CFOP diz o sentido E o destino ao mesmo tempo:
#
#   saída    5 dentro do estado   6 interestadual   7 exterior
#   entrada  1 dentro do estado   2 interestadual   3 exterior
#
# Por isso 5101 e 6101 são a MESMA operação -- muda só para onde vai. É o que
# torna seguro trocar um pelo outro conforme a UF do destinatário.
PRIMEIRO_DIGITO = {
    (SAIDA, DESTINO_INTERNA): '5',
    (SAIDA, DESTINO_INTERESTADUAL): '6',
    (SAIDA, DESTINO_EXTERIOR): '7',
    (ENTRADA, DESTINO_INTERNA): '1',
    (ENTRADA, DESTINO_INTERESTADUAL): '2',
    (ENTRADA, DESTINO_EXTERIOR): '3',
}


def cfop_para_destino(codigo, local):
    """O CFOP equivalente para o destino real da operação.

    O imposto que carrega o CFOP é fixo — `ICMS 41 - CFOP 5101 - EDLAB` — e a
    posição fiscal o entrega igual para São Paulo e para o Rio. Sem esta
    conversão, uma venda interestadual sairia com CFOP de operação interna, que
    é erro fiscal mesmo quando a SEFAZ deixa passar.

    Devolve None quando não há o que decidir (código torto, ou já correto).
    """
    digitos = only_digits(codigo)
    if not digitos or len(digitos) != 4:
        return None
    tipo = tipo_documento_por_cfop(digitos)
    if tipo is None:
        return None
    novo = PRIMEIRO_DIGITO.get((tipo, local))
    if not novo or novo == digitos[0]:
        return None
    return novo + digitos[1:]


def cst_icms_padrao(regime_tributario):
    """No Simples o campo carrega CSOSN; no regime normal, CST. Nomes iguais,
    tabelas diferentes -- trocar um pelo outro é rejeição 'CST inválido'."""
    if regime_tributario in (CRT_SIMPLES, CRT_SIMPLES_EXCESSO):
        return CSOSN_SIMPLES_IMUNE
    return CST_ICMS_NAO_TRIBUTADA


# ----------------------------------------------------------------------
# montagem
# ----------------------------------------------------------------------

def build_item(indice, item, regime_tributario):
    """Monta um item do array `items`.

    `item` é um dicionário nosso, com nomes de negócio; o retorno usa os nomes
    da Focus.
    """
    quantidade = Decimal(str(item.get('quantidade') or 0))
    unitario = Decimal(str(item.get('valor_unitario') or 0))
    # O bruto é quantidade * unitário, calculado aqui e não recebido pronto:
    # se ele não fechar com o total da nota, a SEFAZ rejeita.
    bruto = item.get('valor_bruto')
    if bruto is None:
        bruto = quantidade * unitario

    cst_icms = item.get('icms_situacao_tributaria') or cst_icms_padrao(regime_tributario)

    linha = {
        'numero_item': indice,
        'codigo_produto': texto(item.get('codigo'), 60),
        'descricao': texto(item.get('descricao'), 120),
        'codigo_ncm': only_digits(item.get('ncm')),
        'cfop': only_digits(item.get('cfop')),
        'unidade_comercial': texto(item.get('unidade') or 'UN', 6),
        'quantidade_comercial': money(quantidade, 4),
        'valor_unitario_comercial': money(unitario, 10),
        'valor_bruto': money(bruto),
        # A SEFAZ exige a unidade tributável mesmo quando é igual à comercial.
        'unidade_tributavel': texto(item.get('unidade') or 'UN', 6),
        'quantidade_tributavel': money(quantidade, 4),
        'valor_unitario_tributavel': money(unitario, 10),
        'icms_origem': item.get('icms_origem', 0),
        'icms_situacao_tributaria': cst_icms,
        'pis_situacao_tributaria': item.get(
            'pis_situacao_tributaria') or CST_PIS_COFINS_ALIQUOTA_ZERO,
        'cofins_situacao_tributaria': item.get(
            'cofins_situacao_tributaria') or CST_PIS_COFINS_ALIQUOTA_ZERO,
        'inclui_no_total': item.get('inclui_no_total', 1),
    }

    # O cBenef acompanha o CST, não o produto: o mesmo livro numa operação
    # tributada não leva código nenhum.
    cbenef = item.get('codigo_beneficio_fiscal')
    if cbenef and cst_icms in CST_QUE_PEDEM_CBENEF:
        linha['codigo_beneficio_fiscal'] = cbenef

    # Grupo IBS/CBS, obrigatório desde 30/07/2026. Os dois campos andam juntos:
    # a classificação tem de ser compatível com o CST, e a SEFAZ confere.
    cst_ibs_cbs = item.get('ibs_cbs_situacao_tributaria')
    class_trib = item.get('ibs_cbs_classificacao_tributaria')
    if cst_ibs_cbs:
        linha['ibs_cbs_situacao_tributaria'] = cst_ibs_cbs
    if class_trib:
        linha['ibs_cbs_classificacao_tributaria'] = class_trib

    # Documento referenciado POR ITEM (reforma tributária). Numa devolução não
    # basta referenciar a nota no cabeçalho: a SEFAZ recusa com "NF-e de
    # devolução de mercadoria não possui documento fiscal referenciado por
    # item" até saber QUAL item da nota original cada linha devolve.
    chave_ref = only_digits(item.get('chave_dfe_referenciado'))
    if chave_ref and len(chave_ref) == 44:
        linha['chave_acesso_dfe_referenciado'] = chave_ref
        numero_ref = item.get('numero_item_dfe_referenciado')
        if numero_ref:
            linha['numero_item_dfe_referenciado'] = str(numero_ref)

    # Campos que só existem quando há tributo de fato. Mandar `icms_aliquota: 0`
    # numa nota imune faz a SEFAZ reclamar do grupo de tributação.
    for origem, destino in (
        ('icms_aliquota', 'icms_aliquota'),
        ('icms_base_calculo', 'icms_base_calculo'),
        ('icms_valor', 'icms_valor'),
        ('pis_aliquota_porcentual', 'pis_aliquota_porcentual'),
        ('pis_base_calculo', 'pis_base_calculo'),
        ('pis_valor', 'pis_valor'),
        ('cofins_aliquota_porcentual', 'cofins_aliquota_porcentual'),
        ('cofins_base_calculo', 'cofins_base_calculo'),
        ('cofins_valor', 'cofins_valor'),
        ('valor_desconto', 'valor_desconto'),
        ('valor_frete', 'valor_frete'),
        ('cest', 'cest'),
        ('codigo_barras_comercial', 'codigo_barras_comercial'),
        ('codigo_barras_tributavel', 'codigo_barras_tributavel'),
    ):
        if item.get(origem) not in (None, ''):
            valor = item[origem]
            linha[destino] = money(valor) if origem != 'cest' and not isinstance(
                valor, str) else valor

    return linha


def build_payload(nota, emitente, destinatario, itens, transportador=None):
    """Monta o JSON completo da NFe.

    :param nota: natureza_operacao, data_emissao (ISO 8601 com fuso),
        tipo_documento, finalidade_emissao, consumidor_final,
        presenca_comprador, modalidade_frete, valores e observações.
    :param emitente: cnpj, nome, inscricao_estadual, regime_tributario e endereço.
    :param destinatario: nome, cnpj/cpf, inscricao_estadual, indicador_ie e endereço.
    :param itens: lista de dicionários no formato aceito por `build_item`.
    :param transportador: nome, cnpj/cpf, inscricao_estadual, endereco (linha
        única), municipio e uf -- ou None, quando a nota não declara
        transportadora. Quem decide se o grupo entra é o chamador: com
        modalidade 9 (sem ocorrência de transporte) ele não deve vir.
    :return: dicionário pronto para `FocusClient.emitir_nfe`.
    """
    regime = emitente.get('regime_tributario') or CRT_NORMAL
    uf_emit = (emitente.get('uf') or '').strip().upper()
    uf_dest = (destinatario.get('uf') or '').strip().upper()

    linhas = [build_item(i, item, regime) for i, item in enumerate(itens, start=1)]

    # O total dos produtos é a soma dos brutos dos itens que entram no total.
    # Recalculado aqui, e não copiado do Odoo, porque é a soma dos valores JÁ
    # arredondados que a SEFAZ confere -- arredondar depois de somar dá centavo
    # de diferença e rejeição.
    valor_produtos = sum(
        Decimal(linha['valor_bruto']) for linha in linhas
        if linha.get('inclui_no_total', 1) and linha.get('valor_bruto'))

    frete = Decimal(str(nota.get('valor_frete') or 0))
    seguro = Decimal(str(nota.get('valor_seguro') or 0))
    outras = Decimal(str(nota.get('valor_outras_despesas') or 0))

    # O desconto da NOTA é a soma dos descontos dos ITENS -- a SEFAZ confere
    # exatamente isso (ICMSTot/vDesc = soma de det/prod/vDesc), e é também o que
    # faz o desconto aparecer no DANFE.
    #
    # Somar os valores JÁ arredondados, como em `valor_produtos`: arredondar
    # depois de somar dá centavo de diferença, e diferença de centavo aqui é
    # rejeição.
    desconto_dos_itens = sum(
        (Decimal(linha['valor_desconto']) for linha in linhas
         if linha.get('valor_desconto')), Decimal(0))
    # O desconto de cabeçalho só vale quando nenhum item tem o seu: um número
    # solto no total que não corresponde à soma dos itens é rejeitado.
    desconto = desconto_dos_itens or Decimal(str(nota.get('valor_desconto') or 0))

    valor_total = nota.get('valor_total')
    if valor_total is None:
        valor_total = valor_produtos + frete + seguro + outras - desconto

    payload = {
        # -- identificação da nota ------------------------------------
        'natureza_operacao': texto(nota.get('natureza_operacao'), 60),
        'data_emissao': nota.get('data_emissao'),
        'data_entrada_saida': nota.get('data_entrada_saida') or nota.get('data_emissao'),
        'tipo_documento': nota.get('tipo_documento', SAIDA),
        'finalidade_emissao': nota.get('finalidade_emissao', FINALIDADE_NORMAL),
        'local_destino': nota.get('local_destino') or local_destino(uf_emit, uf_dest),
        'consumidor_final': nota.get('consumidor_final', 0),
        'presenca_comprador': nota.get('presenca_comprador', PRESENCA_OUTROS),
        'modalidade_frete': nota.get('modalidade_frete', FRETE_SEM),

        # -- emitente --------------------------------------------------
        'cnpj_emitente': only_digits(emitente.get('cnpj')),
        'nome_emitente': texto(emitente.get('nome'), 60),
        'nome_fantasia_emitente': texto(emitente.get('nome_fantasia'), 60),
        'logradouro_emitente': texto(emitente.get('logradouro'), 60),
        'numero_emitente': texto(emitente.get('numero'), 60),
        'complemento_emitente': texto(emitente.get('complemento'), 60),
        'bairro_emitente': texto(emitente.get('bairro'), 60),
        'municipio_emitente': texto(emitente.get('municipio'), 60),
        'uf_emitente': uf_emit or None,
        'cep_emitente': only_digits(emitente.get('cep')),
        'telefone_emitente': only_digits(emitente.get('telefone')),
        'inscricao_estadual_emitente': only_digits(emitente.get('inscricao_estadual')),
        'regime_tributario': regime,

        # -- destinatário ----------------------------------------------
        'nome_destinatario': texto(destinatario.get('nome'), 60),
        'logradouro_destinatario': texto(destinatario.get('logradouro'), 60),
        'numero_destinatario': texto(destinatario.get('numero'), 60),
        'complemento_destinatario': texto(destinatario.get('complemento'), 60),
        'bairro_destinatario': texto(destinatario.get('bairro'), 60),
        'municipio_destinatario': texto(destinatario.get('municipio'), 60),
        'uf_destinatario': uf_dest or None,
        'cep_destinatario': only_digits(destinatario.get('cep')),
        'telefone_destinatario': only_digits(destinatario.get('telefone')),
        'email_destinatario': texto(destinatario.get('email'), 60),
        'pais_destinatario': texto(destinatario.get('pais'), 60),

        # -- totais ----------------------------------------------------
        'valor_produtos': money(valor_produtos),
        'valor_total': money(valor_total),
        'valor_frete': money(frete),
        'valor_seguro': money(seguro),
        'valor_desconto': money(desconto),
        'valor_outras_despesas': money(outras),

        'informacoes_adicionais_contribuinte': texto(
            nota.get('informacoes_adicionais'), 2000),

        'items': linhas,
    }

    # CNPJ e CPF são mutuamente exclusivos: mandar os dois (ou o vazio) rejeita.
    cnpj_dest = only_digits(destinatario.get('cnpj'))
    cpf_dest = only_digits(destinatario.get('cpf'))
    documento = cnpj_dest or cpf_dest
    if documento and len(documento) == 14:
        payload['cnpj_destinatario'] = documento
    elif documento and len(documento) == 11:
        payload['cpf_destinatario'] = documento

    # Transportadora (grupo transp/transporta). Só quando o chamador mandou:
    # nota sem transporte declarado (modalidade 9) não leva o grupo -- seria
    # nomear quem carrega uma carga que oficialmente não anda.
    if transportador:
        payload['nome_transportador'] = texto(transportador.get('nome'), 60)
        doc_transp = only_digits(transportador.get('cnpj')) or only_digits(
            transportador.get('cpf'))
        if doc_transp and len(doc_transp) == 14:
            payload['cnpj_transportador'] = doc_transp
        elif doc_transp and len(doc_transp) == 11:
            payload['cpf_transportador'] = doc_transp
        ie_transp = only_digits(transportador.get('inscricao_estadual'))
        if ie_transp:
            payload['inscricao_estadual_transportador'] = ie_transp
        for origem, destino, tamanho in (
                ('endereco', 'endereco_transportador', 60),
                ('municipio', 'municipio_transportador', 60)):
            valor = texto(transportador.get(origem), tamanho)
            if valor:
                payload[destino] = valor
        if transportador.get('uf'):
            payload['uf_transportador'] = (
                transportador['uf'] or '').strip().upper()

    # A IE do destinatário só vai quando ele é contribuinte; nos outros casos o
    # indicador sozinho é que responde, e mandar IE junto é erro de schema.
    indicador = destinatario.get('indicador_ie')
    ie_dest = only_digits(destinatario.get('inscricao_estadual'))
    if indicador is None:
        indicador = IE_CONTRIBUINTE if ie_dest else (
            IE_NAO_CONTRIBUINTE if cpf_dest else IE_ISENTO)
    payload['indicador_inscricao_estadual_destinatario'] = indicador
    if indicador == IE_CONTRIBUINTE and ie_dest:
        payload['inscricao_estadual_destinatario'] = ie_dest

    # Série e número só vão quando controlamos a numeração; sem eles a Focus
    # usa a própria sequência do emitente, que é o caminho recomendado.
    for campo in ('serie', 'numero'):
        if nota.get(campo):
            payload[campo] = nota[campo]

    # Volumes e peso (grupo transp/vol). Vão só quando a nota carrega caixa:
    # o acerto de consignação fatura livro que já está na prateleira do
    # cliente e não move volume nenhum -- declarar "1 caixa" ali seria
    # descrever transporte que não houve.
    #
    # É uma LISTA `volumes`, não campos soltos. Campo solto a Focus aceita
    # calada e descarta: a primeira nota de produção saiu com
    # <transp><modFrete>9</modFrete></transp> e nada mais, com o Odoo
    # sabendo o peso. Confirmado em homologação mandando os dois formatos na
    # mesma nota -- só o da lista chegou ao XML (12/08/2026).
    volume = {}
    if nota.get('volumes'):
        volume['quantidade'] = int(nota['volumes'])
        volume['especie'] = texto(nota.get('especie_volumes') or 'CAIXA', 60)
    if nota.get('peso_bruto'):
        # Três casas é o que o schema da NFe aceita em pesoB/pesoL. Só o
        # bruto: peso líquido é outra medida, e repetir o bruto ali seria
        # declarar embalagem de peso zero.
        volume['peso_bruto'] = money(nota['peso_bruto'], casas=3)
    if volume:
        payload['volumes'] = [volume]

    # Cobrança: fatura e duplicatas. Sem isto a nota não diz quando nem em
    # quantas vezes se paga -- e uma venda a prazo sem duplicata é documento
    # incompleto, ainda que a SEFAZ aceite.
    duplicatas = []
    for parcela in (nota.get('duplicatas') or []):
        valor = money(parcela.get('valor'))
        if not valor or Decimal(valor) <= 0:
            continue
        duplicatas.append({
            'numero': texto(parcela.get('numero'), 60),
            'data_vencimento': parcela.get('data_vencimento'),
            'valor': valor,
        })
    # A cobrança não pode passar o total DESTA nota -- ver `abater_excesso`. A
    # parcela zerada pelo abatimento não vira duplicata: duplicata de zero é
    # cobrança que não existe.
    duplicatas = [d for d in abater_excesso(duplicatas, 'valor', valor_total)
                  if Decimal(d['valor']) > 0]
    if duplicatas:
        payload['duplicatas'] = duplicatas
        payload['numero_fatura'] = texto(nota.get('numero_fatura'), 60)
        payload['valor_original_fatura'] = money(valor_produtos + frete + seguro + outras)
        payload['valor_desconto_fatura'] = money(desconto)
        payload['valor_liquido_fatura'] = money(valor_total)

    # Forma de pagamento. O padrão da Focus é 01 (dinheiro), que numa venda a
    # prazo é declaração falsa: quem vende a prazo emite duplicata (14).
    formas = nota.get('formas_pagamento')
    if not formas:
        formas = [{'forma_pagamento': (FORMA_DUPLICATA if duplicatas
                                       else FORMA_SEM_PAGAMENTO),
                   'valor_pagamento': valor_total}]
    # A rejeição 866 é esta: "Ausência de troco quando o valor dos pagamentos
    # informados for maior que o total da nota". Troco é coisa de balcão; aqui
    # o excedente é o centavo do arredondamento, e ele sai do pagamento.
    payload['formas_pagamento'] = abater_excesso(
        [{'forma_pagamento': f.get('forma_pagamento'),
          'valor_pagamento': money(f.get('valor_pagamento'))}
         for f in formas if f.get('forma_pagamento')],
        'valor_pagamento', valor_total)

    # Notas referenciadas, no CABEÇALHO. Numa devolução é o que amarra a nota
    # nova à original -- sem isso a SEFAZ não sabe o que está sendo devolvido.
    #
    # Mas os dois níveis de referência são MUTUAMENTE EXCLUSIVOS: mandar a nota
    # no cabeçalho e o item na linha dá "NF-e com referenciamento de documento
    # a nível de nota e a nível de item". Como a devolução exige o nível de
    # item, é o cabeçalho que sai quando os dois existem.
    tem_referencia_por_item = any(
        linha.get('chave_acesso_dfe_referenciado') for linha in linhas)
    referencias = [only_digits(c) for c in (nota.get('notas_referenciadas') or [])]
    referencias = [c for c in referencias if c and len(c) == 44]
    if referencias and not tem_referencia_por_item:
        payload['notas_referenciadas'] = [{'chave_nfe': c} for c in referencias]

    return {k: v for k, v in payload.items() if v is not None}


def missing_fields(payload):
    """Diz o que falta ANTES de gastar uma chamada na Focus.

    Devolve uma lista de nomes de campo -- vazia quando o payload passa. Não
    substitui a validação da Focus (que é bem mais completa), só evita o
    ida-e-volta nos erros óbvios.
    """
    # `not valor` reprovaria `tipo_documento: 0`, que é nota de ENTRADA e é
    # perfeitamente válido -- o mesmo tropeço do `icms_origem: 0`. Zero é um
    # valor, ausência é None.
    faltando = [c for c in CAMPOS_OBRIGATORIOS_NOTA
                if payload.get(c) is None or payload.get(c) == '']

    if not (payload.get('cnpj_destinatario') or payload.get('cpf_destinatario')):
        faltando.append('cnpj_destinatario/cpf_destinatario')

    itens = payload.get('items') or []
    if not itens:
        faltando.append('items')
    for item in itens:
        numero = item.get('numero_item', '?')
        for campo in CAMPOS_OBRIGATORIOS_ITEM:
            valor = item.get(campo)
            # icms_origem = 0 é válido; `not 0` seria um falso positivo.
            if valor is None or valor == '':
                faltando.append('items[%s].%s' % (numero, campo))

    return faltando
