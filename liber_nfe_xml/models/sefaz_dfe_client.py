# -*- coding: utf-8 -*-
"""Thin client for the SEFAZ NFeDistribuicaoDFe web service (Ambiente Nacional).

Plain Python (no Odoo model): mutual-TLS session built from an A1 (.pfx)
certificate, SOAP 1.2 envelope, NSU sweep parsing. The service returns the
FULL XML only for notes where the certificate holder is the RECIPIENT;
for notes the holder emitted it returns events (cancellations, CCe) and
summaries — the item-level XML of an emitted note only exists in the
emitting system.

Relevant cStat codes: 137 = no new documents, 138 = documents found,
656 = rate limited (retry in ~1h).
"""
import base64
import gzip
import os
import ssl
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

URL = 'https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx'
WSDLNS = 'http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe'
NFENS = 'http://www.portalfiscal.inf.br/nfe'

CSTAT_NO_DOCS = '137'
CSTAT_RATE_LIMITED = '656'


def _lname(tag):
    return tag.split('}')[-1]


def _find(el, name):
    for e in el.iter():
        if _lname(e.tag) == name:
            return e
    return None


def _text(el, name):
    e = _find(el, name)
    return e.text if e is not None else None


class DfeClient(object):

    def __init__(self, pfx_bytes, password, uf='35', amb='1'):
        from cryptography.hazmat.primitives.serialization import (
            pkcs12, Encoding, PrivateFormat, NoEncryption)
        key, cert, extra = pkcs12.load_key_and_certificates(
            pfx_bytes, password.encode() if password else None)
        if key is None or cert is None:
            raise ValueError('PFX without a usable key/certificate pair')
        self._cert_pem = cert.public_bytes(Encoding.PEM) + b''.join(
            c.public_bytes(Encoding.PEM) for c in (extra or []))
        self._key_pem = key.private_bytes(
            Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())
        self.subject = cert.subject.rfc4514_string()
        self.not_valid_after = getattr(cert, 'not_valid_after_utc', None) or cert.not_valid_after
        self.uf = uf
        self.amb = amb
        self._ctx_cache = {}

    def _ctx(self, verify):
        if verify not in self._ctx_cache:
            if verify:
                ctx = ssl.create_default_context()
            else:
                # The ICP-Brasil chain is often absent from the default trust
                # store; client (mutual) authentication stays active.
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            cf = tempfile.NamedTemporaryFile(delete=False, suffix='.pem')
            cf.write(self._cert_pem)
            cf.close()
            kf = tempfile.NamedTemporaryFile(delete=False, suffix='.pem')
            kf.write(self._key_pem)
            kf.close()
            os.chmod(kf.name, 0o600)
            try:
                ctx.load_cert_chain(cf.name, kf.name)
            finally:
                for p in (cf.name, kf.name):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
            self._ctx_cache[verify] = ctx
        return self._ctx_cache[verify]

    def envelope(self, cnpj, ult_nsu=None, chave=None):
        if chave:
            cons = '<consChNFe><chNFe>%s</chNFe></consChNFe>' % chave
        else:
            cons = '<distNSU><ultNSU>%015d</ultNSU></distNSU>' % int(ult_nsu or 0)
        return ('<?xml version="1.0" encoding="UTF-8"?>'
                '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope"><soap12:Body>'
                '<nfeDistDFeInteresse xmlns="%s"><nfeDadosMsg>'
                '<distDFeInt xmlns="%s" versao="1.35">'
                '<tpAmb>%s</tpAmb><cUFAutor>%s</cUFAutor><CNPJ>%s</CNPJ>%s'
                '</distDFeInt></nfeDadosMsg></nfeDistDFeInteresse></soap12:Body></soap12:Envelope>'
                ) % (WSDLNS, NFENS, self.amb, self.uf, cnpj, cons)

    def post(self, envelope_xml):
        req = urllib.request.Request(
            URL, data=envelope_xml.encode('utf-8'),
            headers={'Content-Type': 'application/soap+xml; charset=utf-8',
                     'Accept': 'application/soap+xml'})
        try:
            with urllib.request.urlopen(req, context=self._ctx(True), timeout=90) as r:
                return r.read().decode('utf-8', 'replace')
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLCertVerificationError):
                with urllib.request.urlopen(req, context=self._ctx(False), timeout=90) as r:
                    return r.read().decode('utf-8', 'replace')
            raise

    def fetch(self, cnpj, ult_nsu):
        """One distNSU call. Returns the parse_ret() dict."""
        return parse_ret(self.post(self.envelope(cnpj, ult_nsu=ult_nsu)))


def parse_ret(xml_text):
    """Parse a NFeDistribuicaoDFe SOAP response into a plain dict:
    {cStat, xMotivo, ultNSU, maxNSU, docs: [{nsu, schema, xml(bytes)}]}."""
    root = ET.fromstring(xml_text)
    ret = _find(root, 'retDistDFeInt')
    if ret is None:
        fault = _find(root, 'Text') or _find(root, 'faultstring')
        raise RuntimeError('Response without retDistDFeInt. %s' % (
            fault.text if fault is not None and fault.text else xml_text[:400]))
    out = {'cStat': _text(ret, 'cStat'), 'xMotivo': _text(ret, 'xMotivo'),
           'ultNSU': _text(ret, 'ultNSU'), 'maxNSU': _text(ret, 'maxNSU'), 'docs': []}
    lote = _find(ret, 'loteDistDFeInt')
    if lote is not None:
        for dz in lote.iter():
            if _lname(dz.tag) != 'docZip':
                continue
            raw = gzip.decompress(base64.b64decode(dz.text))
            out['docs'].append({'nsu': dz.get('NSU'), 'schema': dz.get('schema', ''), 'xml': raw})
    return out


def doc_family(doc):
    """Root family of a distributed document: procNFe, resNFe, procEventoNFe,
    resEvento... Taken from the schema attribute, falling back to the XML root."""
    fam = (doc.get('schema') or '').split('_')[0]
    if not fam:
        try:
            fam = _lname(ET.fromstring(doc['xml']).tag)
        except Exception:
            fam = 'unknown'
    return fam
