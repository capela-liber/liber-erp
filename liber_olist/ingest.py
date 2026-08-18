"""Ingere os XMLs baixados do Olist (liber_olist/_dump/xml/) no módulo `nfe_xml`.

Roda no odoo shell, reusando exatamente o caminho do wizard de upload — não
altera nenhum model. É o teste do loop Olist → Odoo (NOTES.md §6, Fase 0):

    docker exec -i edlab19-odoo odoo shell -d olist --db_host=db \
        --db_user=odoo --db_password=odoo --no-http < liber_olist/ingest.py
"""
import base64
from pathlib import Path

XMLS = Path("/mnt/extra-addons/liber_olist/_dump/xml")

# --- 1. A empresa precisa ser a real, senão a direção da nota sai errada ------
# identify_parties() decide entrada/saída comparando o CNPJ da nota com o da
# empresa. Com a "My Company" padrão (sem CNPJ), toda nota seria classificada
# errado. Dados vindos do próprio info.php da conta Olist.
company = env.company
company.write({
    "name": "EDLAB PRESS EDITORA LTDA",
    "vat": "35.288.052/0001-90",
    "street": "Rua Milton Ribeiro, 79",
    "street2": "Sala 2 - Vila Guilherme",
    "city": "São Paulo",
    "zip": "02055-060",
})
print(f"empresa: {company.name} / {company.vat}")

Panel = env["nfe.xml.panel"]


def unwrap(envelope: bytes) -> bytes | None:
    """Extrai o <nfeProc> de dentro do envelope <retorno><xml_nfe>…</xml_nfe>.

    Recorte por bytes, de propósito: reparsear e reserializar reescreveria os
    namespaces e invalidaria a assinatura digital da NF-e.
    """
    start = envelope.find(b"<xml_nfe>")
    end = envelope.rfind(b"</xml_nfe>")
    if start == -1 or end == -1:
        return None
    return envelope[start + len(b"<xml_nfe>"):end].strip()


ok = dup = bad = 0
for path in sorted(XMLS.iterdir()):
    xml = unwrap(path.read_bytes())
    if not xml:
        bad += 1
        continue
    # Mesmo gate do wizard: valida o root e recusa chave já importada.
    key = Panel.is_valid_xml_and_nfe_key(xml)
    if not key:
        dup += 1
        continue
    panel = Panel.create({
        "file": base64.encodebytes(xml),
        "file_name": f"olist-{path.stem}.xml",
        "company_id": company.id,
        "key": key,
        "status": "imported",
    })
    panel.identify_parties()
    ok += 1

env.cr.commit()
print(f"ingeridos={ok} duplicados/recusados={dup} sem_xml_nfe={bad}")

# --- 2. Parseia (mesmo método que o cron dispara sozinho a cada 10 min) -------
pend = Panel.search([("status", "=", "imported")])
print(f"parseando {len(pend)} panels…")
pend.action_import_xml_file()
env.cr.commit()

for status in ("valid", "error", "imported", "cancelled"):
    n = Panel.search_count([("status", "=", status)])
    if n:
        print(f"  status={status}: {n}")
