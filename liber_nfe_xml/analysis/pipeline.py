# -*- coding: utf-8 -*-
"""Payload builder for the embedded XML analytics panel.

Adapted from the standalone "Painel Editora Campos" pipeline: produces the
same compact payload consumed by static/panel/panel_template.html, but reads
NFe XML bytes handed in by the controller (no filesystem) and supports the
multi-company house (a set of CNPJ roots) instead of a single CNPJ.

Only notes EMITTED by a house company enter the analysis: the panel is
seller-centric (revenue, consignment aging, client base). Notes received
from third parties are counted in meta and skipped. Cancelled notes must be
filtered out by the caller (the panel record status carries that).
"""
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter
from datetime import date

NS = {'n': 'http://www.portalfiscal.inf.br/nfe'}

CFOP_CAT = {
 '5101': 'VENDA', '6101': 'VENDA', '7102': 'VENDA', '5102': 'VENDA', '6102': 'VENDA', '5103': 'VENDA', '5104': 'VENDA', '5108': 'VENDA', '6108': 'VENDA',
 '5113': 'ACERTO_CONSIGNACAO', '6113': 'ACERTO_CONSIGNACAO', '5114': 'ACERTO_CONSIGNACAO', '6114': 'ACERTO_CONSIGNACAO',
 '5917': 'REMESSA_CONSIGNACAO', '6917': 'REMESSA_CONSIGNACAO', '1918': 'RETORNO_CONSIGNACAO', '2918': 'RETORNO_CONSIGNACAO',
 '5904': 'REMESSA_VENDA_FORA', '6904': 'REMESSA_VENDA_FORA', '1904': 'RETORNO_VENDA_FORA', '2904': 'RETORNO_VENDA_FORA',
 '5151': 'TRANSFERENCIA', '6151': 'TRANSFERENCIA', '5152': 'TRANSFERENCIA', '6152': 'TRANSFERENCIA', '1152': 'TRANSFERENCIA', '2152': 'TRANSFERENCIA',
 '1201': 'DEVOLUCAO_VENDA', '2201': 'DEVOLUCAO_VENDA', '1202': 'DEVOLUCAO_VENDA', '2202': 'DEVOLUCAO_VENDA',
 '5910': 'BONIFICACAO', '6910': 'BONIFICACAO', '1910': 'BONIFICACAO', '5927': 'BAIXA_ESTOQUE', '5901': 'REMESSA_INDUSTRIALIZACAO',
 # CFOPs genericos usados apenas como remessa simples / transferencia de mercadoria (NAO sao venda)
 '5949': 'REMESSA_SIMPLES', '6949': 'REMESSA_SIMPLES', '7949': 'REMESSA_SIMPLES', '1949': 'REMESSA_SIMPLES', '2949': 'REMESSA_SIMPLES',
}
RECEITA_CAT = {'VENDA', 'ACERTO_CONSIGNACAO'}


def _t(el, p):
    if el is None:
        return ''
    f = el.find(p, NS)
    return f.text if f is not None and f.text else ''


def canal(no):
    u = (no or '').upper()
    if 'INTERNET' in u: return 'Internet'
    if 'PRE-VENDA' in u or 'PRÉ' in u: return 'Pré-venda'
    if 'CATARSE' in u: return 'Catarse'
    if 'EBOOK' in u: return 'E-book'
    if 'COLABORADOR' in u: return 'Cota colaborador'
    if 'CONSIGNA' in u: return 'Consignação (acerto)'
    if 'POD' in u: return 'POD'
    if 'BALCAO' in u or 'BALCÃO' in u: return 'Balcão'
    if 'ESPECIAL' in u: return 'Venda especial'
    return 'Venda direta/atacado'


CANAIS = ['Venda direta/atacado', 'Consignação (acerto)', 'Internet', 'Pré-venda', 'Catarse', 'E-book', 'Cota colaborador', 'POD', 'Balcão', 'Venda especial']


def parse(xml_items, own_roots, root_label):
    """Parse an iterable of (xml_bytes, record_ref) into note/item rows.

    own_roots: set of 8-digit CNPJ roots of the house companies.
    root_label: {root: company display name} for the "unidade" axis.
    Returns (notas, itens, unids, stats).
    """
    seen = set()
    notas, itens, unids = [], [], []
    uix = {}
    stats = {'recebidas': 0, 'invalidas': 0, 'eventos': 0}
    for raw, ref in xml_items:
        try:
            root = ET.fromstring(raw)
        except Exception:
            stats['invalidas'] += 1
            continue
        if root.tag.split('}')[-1] == 'procEventoNFe':
            stats['eventos'] += 1
            continue
        inf = root.find('.//n:infNFe', NS)
        if inf is None:
            stats['invalidas'] += 1
            continue
        chave = inf.get('Id', '').replace('NFe', '')
        if chave in seen:
            continue
        seen.add(chave)
        ide = inf.find('n:ide', NS); emit = inf.find('n:emit', NS)
        dest = inf.find('n:dest', NS); tot = inf.find('.//n:ICMSTot', NS)
        ec = _t(emit, 'n:CNPJ')
        if ec[:8] not in own_roots:
            stats['recebidas'] += 1
            continue
        lbl = root_label.get(ec[:8]) or ec[:8]
        if lbl not in uix:
            uix[lbl] = len(unids)
            unids.append(lbl)
        uni = uix[lbl]
        dh = (_t(ide, 'n:dhEmi') or _t(ide, 'n:dEmi'))[:10]
        tp = _t(ide, 'n:tpNF'); no = _t(ide, 'n:natOp')
        dd = _t(dest, 'n:CNPJ') or _t(dest, 'n:CPF'); dn = _t(dest, 'n:xNome')
        en = dest.find('n:enderDest', NS) if dest is not None else None
        uf = _t(en, 'n:UF'); mun = _t(en, 'n:xMun')
        interno = dd[:8] in own_roots
        notas.append({'chave': chave, 'data': dh, 'ano_mes': dh[:7], 'nNF': _t(ide, 'n:nNF'), 'serie': _t(ide, 'n:serie'), 'tpNF': tp, 'natOp': no,
            'unidade': uni, 'emit_cnpj': ec, 'dest_doc': dd, 'dest_nome': dn, 'uf': uf, 'mun': mun, 'dest_interno': int(interno), 'path': str(ref),
            'vNF': float(_t(tot, 'n:vNF') or 0), 'vProd': float(_t(tot, 'n:vProd') or 0), 'vICMS': float(_t(tot, 'n:vICMS') or 0)})
        for det in inf.findall('n:det', NS):
            pr = det.find('n:prod', NS); cf = _t(pr, 'n:CFOP'); cat = CFOP_CAT.get(cf, 'OUTRA')
            rec = 1 if (cat in RECEITA_CAT and not interno) else 0
            itens.append({'chave': chave, 'data': dh, 'ano_mes': dh[:7], 'tpNF': tp, 'natOp': no, 'unidade': uni,
                'dest_doc': dd, 'dest_nome': dn, 'dest_interno': int(interno), 'uf': uf, 'mun': mun,
                'cProd': _t(pr, 'n:cProd'), 'xProd': _t(pr, 'n:xProd'), 'ncm': _t(pr, 'n:NCM'), 'cfop': cf, 'categoria': cat,
                'is_receita': rec, 'qCom': float(_t(pr, 'n:qCom') or 0), 'vUnCom': float(_t(pr, 'n:vUnCom') or 0),
                'vProd': float(_t(pr, 'n:vProd') or 0), 'vDesc': float(_t(pr, 'n:vDesc') or 0)})
    return notas, itens, unids, stats


def build_payload(notas, itens, unids, own_roots, stats):
    datas = sorted(set(r['data'] for r in itens if r['data']))
    if not datas:
        return None
    REF = date.fromisoformat(datas[-1])
    dd = lambda d: (REF - date.fromisoformat(d)).days if d else None
    MONTHS = sorted(set(r['ano_mes'] for r in itens if r['ano_mes'])); mI = {m: i for i, m in enumerate(MONTHS)}
    CATS = sorted(set(r['categoria'] for r in itens)); cI = {c: i for i, c in enumerate(CATS)}; canI = {c: i for i, c in enumerate(CANAIS)}
    CFOPS = sorted(set(r['cfop'] for r in itens)); cfI = {c: i for i, c in enumerate(CFOPS)}
    nomeOf = defaultdict(str); ufOf = {}; titC = defaultdict(Counter)
    for r in itens:
        d = r['dest_doc']
        if len(r['dest_nome']) > len(nomeOf[d]): nomeOf[d] = r['dest_nome']
        ufOf[d] = r['uf']; titC[r['cProd']][r['xProd']] += 1
    cliMap = {}; cliL = []; prodMap = {}; prodL = []; noteIx = {}
    def ci(d):
        if d not in cliMap: cliMap[d] = len(cliL); cliL.append([d, (nomeOf[d] or '')[:46], ufOf[d] or ''])
        return cliMap[d]
    def pi(c):
        if c not in prodMap: prodMap[c] = len(prodL); prodL.append([c, (titC[c].most_common(1)[0][0] or '')[:52]])
        return prodMap[c]
    def ni(ch):
        if ch not in noteIx: noteIx[ch] = len(noteIx)
        return noteIx[ch]
    ITENS = []
    for r in itens:
        # _V (idx 5) = valor LIQUIDO (vProd - vDesc); _VG (11) = bruto/capa; _VD (12) = desconto
        ITENS.append([mI[r['ano_mes']], r['unidade'], ci(r['dest_doc']), pi(r['cProd']),
            round(r['qCom'], 3), round(r['vProd'] - r['vDesc'], 2), cI[r['categoria']],
            canI[canal(r['natOp'])] if r['is_receita'] else -1, r['is_receita'], ni(r['chave']), cfI[r['cfop']],
            round(r['vProd'], 2), round(r['vDesc'], 2)])
    con = defaultdict(lambda: {'rem': 0., 'remq': 0., 'ace': 0., 'aceq': 0., 'ret': 0., 'retq': 0., 'dace': [], 'drem': []})
    for r in itens:
        if r['dest_interno']: continue
        e = con[r['dest_doc']]; c = r['categoria']
        vliq = r['vProd'] - r['vDesc']   # valores de consignacao em LIQUIDO (com desconto)
        if c == 'REMESSA_CONSIGNACAO': e['rem'] += vliq; e['remq'] += r['qCom']; e['drem'].append(r['data'])
        elif c == 'ACERTO_CONSIGNACAO': e['ace'] += vliq; e['aceq'] += r['qCom']; e['dace'].append(r['data'])
        elif c == 'RETORNO_CONSIGNACAO': e['ret'] += vliq; e['retq'] += r['qCom']
    PRECONS = {}
    for d, e in con.items():
        if e['rem'] <= 0: continue
        lastA = max(e['dace']) if e['dace'] else None
        PRECONS[d] = {'rem': round(e['rem'], 2), 'ace': round(e['ace'], 2), 'ret': round(e['ret'], 2),
            'saldo': round(e['rem'] - e['ace'] - e['ret'], 2), 'saldoq': round(e['remq'] - e['aceq'] - e['retq']),
            'lastA': lastA or 'NUNCA', 'lastR': max(e['drem']) if e['drem'] else None,
            'days': dd(lastA) if lastA else dd(min(e['drem'])), 'never': 0 if e['dace'] else 1}
    buy = defaultdict(list)
    for r in itens:
        if r['is_receita'] and not r['dest_interno']: buy[r['dest_doc']].append(r['data'])
    PRECLI = {}
    for d, ds in buy.items():
        u = sorted(set(ds))
        avg = (sum((date.fromisoformat(u[i + 1]) - date.fromisoformat(u[i])).days for i in range(len(u) - 1)) / (len(u) - 1)) if len(u) >= 2 else None
        dl = dd(u[-1]); PRECLI[d] = {'n': len(u), 'first': u[0], 'last': u[-1], 'avg': round(avg, 1) if avg else None, 'dlast': dl, 'overdue': 1 if (avg and dl > avg * 1.5) else 0}
    # NOTES: fonte da verdade — alinhado ao indice de nota usado em ITENS[_N];
    # path carrega o id do registro nfe.xml.panel (nao um caminho de arquivo)
    c2n = {n['chave']: n for n in notas}
    NOTES = [None] * len(noteIx)
    for ch, ix in noteIx.items():
        nt = c2n.get(ch)
        NOTES[ix] = [ch, nt['nNF'], nt['data'], nt['path']] if nt else [ch, '', '', '']
    meta = {'ref': str(REF), 'periodo': [datas[0], datas[-1]], 'n_notas': len(noteIx), 'n_itens': len(ITENS), 'own': sorted(own_roots)}
    meta.update(stats)
    return {'meta': meta, 'months': MONTHS, 'cats': CATS, 'canais': CANAIS, 'cfops': CFOPS,
        'cli': cliL, 'prod': prodL, 'itens': ITENS, 'notes': NOTES, 'precons': PRECONS, 'precli': PRECLI,
        'unids': unids}


def build_consig_hist(notas, itens):
    """Consignment aggregation per economic group over the SAME XML base
    (the standalone tool read a separate folder; here there is one base)."""
    catmap = {'REMESSA_CONSIGNACAO': 'R', 'ACERTO_CONSIGNACAO': 'A', 'RETORNO_CONSIGNACAO': 'D'}
    c2n = {n['chave']: n for n in notas}
    monset = set(); titmap = {}
    grp = defaultdict(lambda: {'nome': '', 'uf': '', 'R': defaultdict(float), 'A': defaultdict(float), 'D': defaultdict(float), 'dace': [], 'notes': [],
        'tit': defaultdict(lambda: {'rq': 0., 'rv': 0., 'aq': 0., 'av': 0., 'dq': 0., 'dv': 0., 'lastAce': '', 'lastMov': ''})})
    per_note = defaultdict(list)
    for r in itens:
        if r['dest_interno'] or not r['dest_doc']: continue
        c = catmap.get(r['categoria'])
        if c: per_note[r['chave']].append((c, r))
    for ch, rows in per_note.items():
        nt = c2n.get(ch) or {}
        first = rows[0][1]
        root = first['dest_doc'][:8]; g = grp[root]
        if len(first['dest_nome']) > len(g['nome']): g['nome'] = first['dest_nome']; g['uf'] = first['uf']
        notecat = defaultdict(float); mo = first['ano_mes']; dfull = first['data']
        for c, r in rows:
            v = r['vProd'] - r['vDesc']; q = r['qCom']; mo = r['ano_mes']; dfull = r['data']   # LIQUIDO
            g[c][mo] += v; notecat[c] += v
            if c == 'A': g['dace'].append(mo)
            cp = r['cProd']; xp = r['xProd']
            if cp:
                if len(xp) > len(titmap.get(cp, '')): titmap[cp] = xp
                tt = g['tit'][cp]
                if c == 'R': tt['rq'] += q; tt['rv'] += v
                elif c == 'A': tt['aq'] += q; tt['av'] += v
                else: tt['dq'] += q; tt['dv'] += v
                if c == 'A' and dfull > tt['lastAce']: tt['lastAce'] = dfull
                if dfull > tt['lastMov']: tt['lastMov'] = dfull
        if notecat:
            monset.add(mo); _cc = {'R': 0, 'A': 1, 'D': 2}
            for c, val in notecat.items(): g['notes'].append([ch, nt.get('nNF', ''), dfull, _cc[c], round(val, 2)])
    if not monset:
        return None
    months = sorted(monset); mi = {m: i for i, m in enumerate(months)}
    tlist = sorted(titmap.keys()); tidx = {cp: i for i, cp in enumerate(tlist)}
    titles = [[cp, (titmap[cp] or '')[:52]] for cp in tlist]   # lookup global cProd->titulo
    clients = []; TR = TA = TD = 0.0
    for root, g in grp.items():
        sr = [0.0] * len(months); sa = [0.0] * len(months); sd = [0.0] * len(months)
        for m, v in g['R'].items(): sr[mi[m]] = round(v, 2)
        for m, v in g['A'].items(): sa[mi[m]] = round(v, 2)
        for m, v in g['D'].items(): sd[mi[m]] = round(v, 2)
        R = sum(sr); A = sum(sa); D = sum(sd); TR += R; TA += A; TD += D
        if not (R or A or D): continue
        # tit: [titleIdx, remQ, aceQ, devQ, saldoV, lastMovMonthIdx, lastAceMonthIdx]; saldoQ = remQ-aceQ-devQ (no JS)
        tit = []
        for cp, tt in g['tit'].items():
            lm = mi.get(tt['lastMov'][:7], -1) if tt['lastMov'] else -1
            la = mi.get(tt['lastAce'][:7], -1) if tt['lastAce'] else -1
            tit.append([tidx[cp], round(tt['rq']), round(tt['aq']), round(tt['dq']), round(tt['rv'] - tt['av'] - tt['dv'], 2), lm, la])
        clients.append({'doc': root, 'nome': g['nome'][:46], 'uf': g['uf'], 'R': round(R, 2), 'A': round(A, 2), 'D': round(D, 2),
            'saldo': round(R - A - D, 2), 'conv': round(100 * A / R, 1) if R else 0, 'lastA': max(g['dace']) if g['dace'] else None,
            'sr': sr, 'sa': sa, 'sd': sd, 'notes': g['notes'], 'tit': tit})
    clients.sort(key=lambda x: -x['saldo'])
    return {'meta': {'periodo': [months[0], months[-1]], 'n_clientes': len(clients), 'rem': round(TR, 2), 'ace': round(TA, 2), 'ret': round(TD, 2), 'conv': round(100 * TA / TR, 1) if TR else 0}, 'months': months, 'titles': titles, 'clients': clients}


def build(xml_items, own_roots, root_label):
    """Full payload from XML bytes. Returns None when nothing parseable."""
    notas, itens, unids, stats = parse(xml_items, own_roots, root_label)
    payload = build_payload(notas, itens, unids, own_roots, stats)
    if payload is not None:
        payload['consigHist'] = build_consig_hist(notas, itens)
    return payload
