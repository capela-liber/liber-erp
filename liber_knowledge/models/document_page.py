"""Os manuais do Liber como páginas do wiki (document.page da OCA).

A fonte continua sendo o site: `liber_site/static/docs/`. Aqui só se copia,
e a cópia é segura de repetir:

* página que ninguém tocou é atualizada quando o manual muda -- e a versão
  anterior fica no histórico da própria página;
* página que alguém editou dentro do Odoo NÃO é sobrescrita: a sincronização
  pula e avisa. Quem edita no wiki assume a página; para devolvê-la ao site,
  basta limpar o campo "Manual do Liber" dela.

Roda na instalação e em todo `-u` (data/liber_manuals_sync.xml), e à mão pelo
menu Conhecimento > Configuração > Atualizar manuais do Liber.
"""

import logging
import os

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext, html_sanitize
from odoo.tools.misc import file_path

from ..tools import wiki

_logger = logging.getLogger(__name__)

# A tela de leitura (client action com path `manuais`) é o endereço de uma
# página: link entre manuais aberto de qualquer lugar do Odoo cai nela.
URL_PAGINA = "/odoo/manuais/%d"

# Quantos caracteres de texto em volta do termo buscado a busca devolve.
TRECHO = 90


class DocumentPage(models.Model):
    _inherit = "document.page"

    liber_manual_slug = fields.Char(
        string="Liber Manual",
        readonly=True,
        copy=False,
        index=True,
        help="Manual of the Liber site this page is copied from. While set, "
        "the page is refreshed whenever the manual changes, unless someone "
        "edited it here.",
    )
    liber_manual_hash = fields.Char(readonly=True, copy=False)
    liber_sequence = fields.Integer(
        string="Sequence", default=100,
        help="Order in the Manuals reader; ties are broken by title.")

    @api.depends("history_ids")
    def _compute_history_head(self):
        # Defeito do document_page (19.0.1.0.2): o HEAD é `history_ids[0]`,
        # mas, na mesma transação, a versão recém-criada entra no FIM do cache
        # do one2many -- e o HEAD gravado continua sendo a versão velha. Pela
        # tela não aparece (cada gravação é uma transação); numa sincronização
        # que cria e atualiza de uma vez, a página ficava com o texto antigo.
        # `sorted()` sem chave reordena pelo `_order` do histórico (id DESC).
        # Herdado aqui, e não editado na cópia da OCA -- ver VENDORADOS.md.
        for rec in self:
            rec.history_head = rec.history_ids.sorted()[:1]

    # -- sincronização ---------------------------------------------------
    @api.model
    def _liber_docs_dir(self):
        try:
            return file_path("liber_site/static/docs")
        except FileNotFoundError:
            raise UserError(self.env._(
                "The Liber manuals were not found: the liber_site module "
                "must be in the addons path (it does not need to be installed)."
            )) from None

    @api.model
    def _liber_sync_manuals(self, docs_dir=None):
        """Cria/atualiza a árvore "Manuais do Liber". Devolve os contadores."""
        docs_dir = docs_dir or self._liber_docs_dir()
        try:
            with open(os.path.join(docs_dir, "docs.js"), encoding="utf-8") as fh:
                catalogo = wiki.ler_catalogo(fh.read())
        except (OSError, ValueError) as erro:
            raise UserError(self.env._(
                "Could not read the Liber manuals catalog: %s", erro)) from None

        Page = self.sudo().with_context(active_test=False)
        raiz = self.env.ref("liber_knowledge.page_liber_manuals").sudo()
        existentes = {
            p.liber_manual_slug: p
            for p in Page.search([("liber_manual_slug", "!=", False)])
        }
        stats = {"created": 0, "updated": 0, "unchanged": 0,
                 "edited": [], "missing": []}

        # 1ª passada: toda categoria e página existe, para os links entre
        # manuais já nascerem apontando para o id certo.
        paginas = {}
        for ordem, area in enumerate(catalogo):
            chave = "area:" + area["area"]
            categoria = existentes.get(chave) or Page.create({
                "name": area["area"],
                "type": "category",
                "parent_id": raiz.id,
                "company_id": False,
                "liber_manual_slug": chave,
            })
            # A ordem do site (a da barra lateral do docs.js) é a da árvore.
            if categoria.liber_sequence != (ordem + 1) * 10:
                categoria.liber_sequence = (ordem + 1) * 10
            for posicao, item in enumerate(area["items"]):
                pagina = existentes.get(item["slug"])
                if not pagina:
                    pagina = Page.create({
                        "name": item["title"],
                        "type": "content",
                        "parent_id": categoria.id,
                        "company_id": False,
                        "liber_manual_slug": item["slug"],
                    })
                    stats["created"] += 1
                if pagina.liber_sequence != (posicao + 1) * 10:
                    pagina.liber_sequence = (posicao + 1) * 10
                paginas[item["slug"]] = (pagina, item)
        links = {slug: URL_PAGINA % p.id for slug, (p, _i) in paginas.items()}

        # 2ª passada: o conteúdo.
        History = self.env["document.page.history"].sudo()
        for slug, (pagina, item) in paginas.items():
            caminho = os.path.join(docs_dir, slug + ".html")
            if not os.path.isfile(caminho):
                stats["missing"].append(slug)
                continue
            html = wiki.converter_manual(caminho, slug, links)
            novo = wiki.assinatura(html)
            if pagina.liber_manual_hash == novo:
                stats["unchanged"] += 1
                continue
            atual = pagina.history_head.content
            if pagina.liber_manual_hash and wiki.assinatura(atual) != pagina.liber_manual_hash:
                # Editada no wiki depois da última cópia: a página é de
                # quem editou. Não se sobrescreve trabalho de gente.
                stats["edited"].append(pagina.name)
                continue
            primeira = not pagina.liber_manual_hash
            History.create({
                "page_id": pagina.id,
                "name": "Manual do Liber",
                "summary": "Copiado do site" if primeira else "Atualizado do site",
                "content": html,
            })
            pagina.liber_manual_hash = novo
            if not primeira:
                stats["updated"] += 1
        _logger.info("Manuais do Liber no wiki: %s", stats)
        return stats

    # -- o app na home: nome, ícone e lugar --------------------------------
    APP_NAME = "Manual"
    APP_ICON = "liber_knowledge,static/description/icon.png"
    # O Manual mora ao lado do Treinamento (liber_training), quando ele existe.
    APP_VIZINHO = "liber_training.menu_training_root"

    @api.model
    def _liber_app_name(self):
        """O app se chama "Manual" (25/09/2026), com ícone próprio e ao lado do
        Treinamento, e não "Conhecimento" com o ícone da OCA no fim da home.

        O menu raiz é da OCA e a tradução pt_BR dele ("Conhecimento") já está
        gravada no banco; o `-u` não sobrescreve tradução existente. Por isso
        nome, ícone e sequência vão por aqui, a cada instalação e update
        (data/liber_manuals_sync.xml). "Manual" é o mesmo em pt e em en.
        """
        menu = self.env.ref("document_knowledge.menu_document_root").sudo()
        for code, _nome in self.env["res.lang"].get_installed():
            if menu.with_context(lang=code).name != self.APP_NAME:
                menu.with_context(lang=code).name = self.APP_NAME
        valores = {}
        if menu.web_icon != self.APP_ICON:
            valores["web_icon"] = self.APP_ICON
        vizinho = self.env.ref(self.APP_VIZINHO, raise_if_not_found=False)
        # Uma depois do vizinho, e não a mesma: desempatar pelo id punha o
        # Manual ANTES quando o menu dele era o mais antigo (a vitrine).
        if vizinho and menu.sequence != vizinho.sequence + 1:
            valores["sequence"] = vizinho.sequence + 1
        if valores:
            menu.write(valores)

    # -- tela de leitura ("Manuais") ---------------------------------------
    # A tela é um client action (static/src/reader); estes três métodos são
    # tudo o que ela pede. Todos rodam como o usuário: o que a regra de acesso
    # esconde (página restrita a um grupo) não aparece nem na árvore.
    def _liber_ordem(self):
        return self.sorted(lambda p: (p.liber_sequence, (p.name or "").lower()))

    @api.model
    def liber_reader_tree(self):
        """A árvore visível para o usuário: [{id, name, type, children}]."""
        paginas = self.search([])._liber_ordem()
        nos = {p.id: {"id": p.id, "name": p.name, "type": p.type, "children": []}
               for p in paginas}
        raizes = []
        for p in paginas:
            pai = nos.get(p.parent_id.id)
            # pai invisível (restrito a outro grupo): a página sobe para a raiz
            (pai["children"] if pai else raizes).append(nos[p.id])
        return raizes

    def _liber_caminho(self):
        caminho, atual = [], self.parent_id
        while atual and atual.has_access("read"):
            caminho.insert(0, {"id": atual.id, "name": atual.name})
            atual = atual.parent_id
        return caminho

    def liber_reader_page(self):
        """Uma página (ou categoria) pronta para a tela de leitura."""
        self.ensure_one()
        filhos = self.child_ids._liber_ordem()
        editor = self.env.user.has_group("document_page.group_document_editor")
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "path": self._liber_caminho(),
            # sanitizado na leitura: o campo é sanitize=False na OCA, e o que
            # um editor gravou não deve rodar script no navegador de quem lê.
            # O estilo embutido dos manuais sobrevive (é atributo permitido).
            "content": html_sanitize(self.content) if self.type == "content" else "",
            "children": [{"id": f.id, "name": f.name, "type": f.type,
                          "count": len(f.child_ids)} for f in filhos],
            "can_edit": editor and self.has_access("write"),
            "can_create": editor,
            "last_date": self.content_date,
            # a versão gravada pela sincronização é do OdooBot: não é autor
            "last_user": "" if self.content_uid.id in (False, SUPERUSER_ID)
            else self.content_uid.name,
            "from_site": bool(self.liber_manual_slug and self.type == "content"),
        }

    @api.model
    def liber_reader_search(self, termo, limite=40):
        """Páginas cujo título ou texto contém o termo, com um trecho."""
        termo = (termo or "").strip()
        if len(termo) < 2:
            return []
        paginas = self.search([
            ("type", "=", "content"),
            "|", ("name", "ilike", termo), ("content", "ilike", termo),
        ], limit=limite)
        resultado = []
        for p in sorted(paginas, key=lambda p: (termo.lower() not in (p.name or "").lower(),
                                                p.liber_sequence, p.name or "")):
            texto = " ".join(html2plaintext(p.content or "").split())
            i = texto.lower().find(termo.lower())
            trecho = ""
            if i >= 0:
                ini, fim = max(0, i - TRECHO), i + len(termo) + TRECHO
                trecho = ("…" if ini else "") + texto[ini:fim] + ("…" if fim < len(texto) else "")
            resultado.append({"id": p.id, "name": p.name,
                              "area": p.parent_id.name or "", "snippet": trecho})
        return resultado

    @api.model
    def action_liber_sync_manuals(self):
        if not self.env.user.has_group("document_page.group_document_manager"):
            raise UserError(self.env._(
                "Only a Knowledge manager can update the Liber manuals."))
        stats = self._liber_sync_manuals()
        linhas = [self.env._(
            "%(created)s created, %(updated)s updated, %(unchanged)s unchanged.",
            created=stats["created"], updated=stats["updated"],
            unchanged=stats["unchanged"])]
        if stats["edited"]:
            linhas.append(self.env._(
                "Kept as edited here: %s", ", ".join(stats["edited"])))
        if stats["missing"]:
            linhas.append(self.env._(
                "Manual file missing: %s", ", ".join(stats["missing"])))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Liber manuals"),
                "message": " ".join(linhas),
                "type": "warning" if stats["edited"] or stats["missing"] else "success",
                "sticky": bool(stats["edited"] or stats["missing"]),
            },
        }
