// Documentação do Liber — catálogo dos manuais e montagem da navegação.
// Cada página de manual só precisa de:
//   <aside class="sidebar" id="sidebar"></aside>  … <nav class="pager" id="pager"></nav>
// e este script cuida da sidebar, do destaque da página atual e do anterior/próximo.

var DOCS = [
  { area: "Consignação", desc: "Do acordo com a livraria ao acerto — prateleiras, remessas, cobrança e auditoria.", items: [
    { slug: "liber_soc_agreements", title: "Acordos de consignação", desc: "O contrato com cada livraria e a prateleira que nasce dele." },
    { slug: "liber_soc_moves", title: "Remessas e retornos", desc: "Documentos de consignação: remessa, retorno e o pedido de consignação." },
    { slug: "liber_soc_settlement", title: "Acerto de consignação", desc: "Da contagem do cliente à venda, reposição e devolução em um clique." },
    { slug: "liber_soc_fiscal_br", title: "Fiscal da consignação", desc: "CFOPs, contas contábeis e o estoque consignado sem dupla valoração." },
    { slug: "liber_soc_audit", title: "Auditoria pelo XML", desc: "O saldo de cada prateleira conferido contra as próprias notas fiscais." },
  ]},
  { area: "Direitos autorais", desc: "Contratos, cálculo de royalties, impostos, pagamento e prestação de contas.", items: [
    { slug: "liber_copyright_contracts", title: "Contratos de direitos autorais", desc: "Contratos com beneficiários, obras, vigência e renovação." },
    { slug: "liber_copyright_contracts_analytics", title: "Cálculo de royalties", desc: "Faixas de exemplares, base de cálculo e adiantamentos." },
    { slug: "liber_copyright_contracts_taxes", title: "IRRF sobre direitos", desc: "Retenção pela tabela progressiva e o redutor da Lei 15.270/2025." },
    { slug: "liber_copyright_contracts_payments", title: "Pagamento de royalties", desc: "Direitos em aberto viram fatura de fornecedor por beneficiário." },
    { slug: "liber_copyright_contracts_reports", title: "Prestação de contas", desc: "O extrato do autor em PDF, pronto para enviar." },
  ]},
  { area: "Fiscal", desc: "A nota fiscal dos dois lados: a que sai, a que chega, e o histórico inteiro dentro do sistema.", items: [
    { slug: "liber_nfe_focus", title: "Emissão de NF-e", desc: "Emita a nota modelo 55 direto da fatura; XML e DANFE voltam anexados." },
    { slug: "liber_nfe_xml", title: "Importação de XML de NF-e", desc: "Importe as notas emitidas e recebidas e reconstrua o histórico." },
    { slug: "liber_nfe_remessa", title: "Notas de remessa", desc: "Documentos sem cobrança — consignação, bonificação, eventos." },
  ]},
  { area: "Catálogo", desc: "Metadados do livro entrando e saindo do sistema pelos padrões do mercado.", items: [
    { slug: "liber_metabooks_integration", title: "Integração Metabooks", desc: "Importação por ISBN, catálogo completo e envio ONIX." },
  ]},
  { area: "Canais de venda", desc: "Os pedidos que chegam de fora — cada canal com o seu jeito de pedir.", items: [
    { slug: "liber_amazon_vendor", title: "Amazon Vendor Central", desc: "Pedidos da Amazon lidos, conferidos contra o cadastro e transformados em cotação." },
  ]},
  { area: "Produção", desc: "O livro impresso quando alguém compra — tiragem, frete e entrega.", items: [
    { slug: "liber_metabrasil", title: "Impressão sob demanda (Metabrasil)", desc: "Preço por tiragem, cotação de frete, dropship e acompanhamento da gráfica." },
  ]},
  { area: "Arquivos", desc: "O acervo da editora nas nuvens, com o Odoo de porteiro — mesma disciplina em três estantes.", items: [
    { slug: "liber_dropbox", title: "Arquivos no Dropbox", desc: "Leitura e escrita por pasta, envio, links com prazo e vínculos a autores e títulos." },
    { slug: "liber_gdrive", title: "Arquivos no Google Drive", desc: "O mesmo portão na frente do Drive: pastas por ID, download conferido, miniaturas até de PDF." },
    { slug: "liber_github", title: "Arquivos no GitHub", desc: "Repositório vira pasta, envio vira commit, e o link compartilhado não fura o portão." },
  ]},
  { area: "Gestão", desc: "Orçamento e controle de acesso.", items: [
    { slug: "liber_budget", title: "Orçamento", desc: "Orçado × realizado sobre a contabilidade analítica." },
    { slug: "liber_roles", title: "Papéis de acesso", desc: "Perfis prontos por área e a conta de visitante somente-leitura." },
  ]},
];

(function () {
  var here = location.pathname.split("/").pop() || "index.html";
  var flat = [];
  DOCS.forEach(function (g) { g.items.forEach(function (d) { flat.push(d); }); });

  // sidebar
  var side = document.getElementById("sidebar");
  if (side) {
    DOCS.forEach(function (g) {
      var h = document.createElement("h4");
      h.textContent = g.area;
      side.appendChild(h);
      g.items.forEach(function (d) {
        var a = document.createElement("a");
        a.href = d.slug + ".html";
        a.textContent = d.title;
        if (here === d.slug + ".html") a.className = "current";
        side.appendChild(a);
      });
    });
  }

  // anterior / próximo
  var pager = document.getElementById("pager");
  var idx = flat.findIndex(function (d) { return here === d.slug + ".html"; });
  if (pager && idx >= 0) {
    var prev = flat[idx - 1], next = flat[idx + 1];
    if (prev) pager.insertAdjacentHTML("beforeend",
      '<a class="prev" href="' + prev.slug + '.html"><span class="dir">← Anterior</span>' + prev.title + "</a>");
    else pager.insertAdjacentHTML("beforeend",
      '<a class="prev" href="index.html"><span class="dir">← Início</span>Manuais</a>');
    if (next) pager.insertAdjacentHTML("beforeend",
      '<a class="next" href="' + next.slug + '.html"><span class="dir">Próximo →</span>' + next.title + "</a>");
  }

  // telas ainda não capturadas: mostra o espaço reservado com o arquivo esperado
  document.querySelectorAll("figure.shot img").forEach(function (img) {
    function placeholder() {
      var box = document.createElement("div");
      box.className = "shot-missing";
      box.innerHTML = '<div style="font-size:26px">📷</div><div>Tela a inserir:</div><code>' +
        img.getAttribute("src") + "</code><div>" + (img.alt || "") + "</div>";
      img.replaceWith(box);
    }
    if (img.complete && img.naturalWidth === 0) placeholder();
    else img.addEventListener("error", placeholder);
  });

  // lightbox
  var lb = document.createElement("div");
  lb.className = "lightbox";
  lb.innerHTML = '<img alt=""><div class="cap"></div>';
  document.body.appendChild(lb);
  function closeLb() { lb.classList.remove("on"); document.body.classList.remove("lb-open"); }
  lb.addEventListener("click", closeLb);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeLb(); });
  document.querySelectorAll("figure.shot img").forEach(function (img) {
    img.addEventListener("click", function () {
      lb.querySelector("img").src = img.src;
      var cap = img.closest("figure").querySelector("figcaption");
      lb.querySelector(".cap").textContent = cap ? cap.textContent : "";
      lb.classList.add("on");
      document.body.classList.add("lb-open");
    });
  });
})();

// ---------------------------------------------------------------- busca
// Procura no TEXTO dos manuais, não só nos títulos: quem procura "campanha"
// quer cair na seção que fala de campanha, mesmo que ela more num manual cujo
// nome não diz isso. O índice é montado na primeira busca (baixa as páginas uma
// vez e o navegador as guarda em cache) — a alternativa seria um índice gerado
// no build, que envelhece calado toda vez que alguém edita um manual.
(function () {
  var flat = [];
  DOCS.forEach(function (g) {
    g.items.forEach(function (d) { flat.push({ slug: d.slug, title: d.title, desc: d.desc, area: g.area }); });
  });

  // Dobra acentos SEM mudar o comprimento da string, para que as posições
  // encontradas na versão dobrada sirvam para grifar o texto original.
  function fold(s) {
    var out = "";
    for (var i = 0; i < s.length; i++) {
      var c = s[i].normalize("NFD").replace(/[\u0300-\u036f]/g, "");
      out += c.length === 1 ? c : s[i];
    }
    return out.toLowerCase();
  }

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  var index = null, indexing = null;

  // textContent cola célula com célula ("InventárioA contagem…"), o que gruda
  // duas palavras que não são uma. Aqui cada bloco entra separado por espaço.
  var BLOCK = /^(P|DIV|LI|UL|OL|TD|TH|TR|TABLE|THEAD|TBODY|BR|H1|H2|H3|H4|H5|H6|FIGURE|FIGCAPTION|SECTION)$/;
  function textOf(el) {
    var out = "";
    el.childNodes.forEach(function (n) {
      if (n.nodeType === 3) out += n.data;
      else if (n.nodeType === 1) {
        var inner = textOf(n);
        out += BLOCK.test(n.tagName) ? " " + inner + " " : inner;
      }
    });
    return out;
  }

  // Quebra um manual em seções pelos <h2 id>, que são as âncoras navegáveis.
  // Os <h3> não têm id, então herdam a âncora do <h2> que os contém.
  function parseDoc(entry, html) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var art = doc.querySelector("article.doc");
    if (!art) return [];
    var out = [], cur = { anchor: "", heading: "", buf: [] };
    function flush() {
      // O ‣ dos caminhos de menu é colado no HTML; solto ele para o trecho ler
      // "Consignação ‣ Campanhas" em vez de "Consignação‣Campanhas".
      var text = cur.buf.join(" ").replace(/‣/g, " ‣ ").replace(/\s+/g, " ").trim();
      if (text || cur.heading) {
        out.push({
          slug: entry.slug, docTitle: entry.title, area: entry.area,
          anchor: cur.anchor, heading: cur.heading, text: text,
        });
      }
    }
    Array.prototype.forEach.call(art.children, function (el) {
      var tag = el.tagName;
      if (tag === "H2") {
        flush();
        cur = { anchor: el.id || "", heading: textOf(el).trim(), buf: [] };
      } else if (tag === "H3") {
        var anchor = cur.anchor;
        flush();
        cur = { anchor: anchor, heading: textOf(el).trim(), buf: [] };
      } else if (tag !== "NAV") {
        cur.buf.push(textOf(el));
      }
    });
    flush();
    return out;
  }

  function buildIndex() {
    if (indexing) return indexing;
    indexing = Promise.all(flat.map(function (entry) {
      return fetch(entry.slug + ".html")
        .then(function (r) { return r.ok ? r.text() : ""; })
        .then(function (html) { return html ? parseDoc(entry, html) : []; })
        .catch(function () { return []; });
    })).then(function (chunks) {
      index = [];
      chunks.forEach(function (c) { c.forEach(function (s) {
        s.hay = fold(s.docTitle + " " + s.heading + " " + s.text);
        index.push(s);
      }); });
      // Se nenhuma página pôde ser lida (aberto como file://, por exemplo),
      // ainda dá para procurar pelo catálogo — pouco, mas não nada.
      if (!index.length) {
        index = flat.map(function (e) {
          var s = { slug: e.slug, docTitle: e.title, area: e.area, anchor: "",
                    heading: e.title, text: e.desc };
          s.hay = fold(e.title + " " + e.desc + " " + e.area);
          return s;
        });
      }
      return index;
    });
    return indexing;
  }

  function search(query) {
    var terms = fold(query).split(/\s+/).filter(function (t) { return t.length >= 2; });
    if (!terms.length) return [];
    var hits = [];
    index.forEach(function (s) {
      var score = 0, head = fold(s.docTitle + " " + s.heading);
      for (var i = 0; i < terms.length; i++) {
        var t = terms[i];
        if (s.hay.indexOf(t) === -1) return;          // exige todos os termos
        if (head.indexOf(t) !== -1) score += 12;
        var n = 0, at = 0;
        while ((at = s.hay.indexOf(t, at)) !== -1) { n++; at += t.length; }
        score += Math.min(n, 6);
      }
      hits.push({ sec: s, score: score, terms: terms });
    });
    hits.sort(function (a, b) { return b.score - a.score; });
    return hits.slice(0, 30);
  }

  // Recorta um trecho em volta da primeira ocorrência e grifa todos os termos.
  function snippet(sec, terms) {
    var text = sec.text, hay = fold(text);
    if (!text) return "";
    var first = -1;
    terms.forEach(function (t) {
      var at = hay.indexOf(t);
      if (at !== -1 && (first === -1 || at < first)) first = at;
    });
    if (first === -1) first = 0;
    var from = Math.max(0, first - 80), to = Math.min(text.length, from + 220);
    if (from > 0) { var sp = text.indexOf(" ", from); if (sp !== -1 && sp < first) from = sp + 1; }
    var cut = text.slice(from, to);
    var cutHay = hay.slice(from, to);

    var ranges = [];
    terms.forEach(function (t) {
      var at = 0;
      while ((at = cutHay.indexOf(t, at)) !== -1) { ranges.push([at, at + t.length]); at += t.length; }
    });
    ranges.sort(function (a, b) { return a[0] - b[0]; });

    var html = "", pos = 0;
    ranges.forEach(function (r) {
      if (r[0] < pos) return;                          // sobreposição: ignora
      html += esc(cut.slice(pos, r[0])) + "<mark>" + esc(cut.slice(r[0], r[1])) + "</mark>";
      pos = r[1];
    });
    html += esc(cut.slice(pos));
    return (from > 0 ? "… " : "") + html + (to < text.length ? " …" : "");
  }

  // ------------------------------------------------------------ interface
  var nav = document.querySelector("header.top nav");
  if (!nav) return;

  var box = document.createElement("div");
  box.className = "docsearch";
  box.innerHTML =
    '<input type="search" class="docsearch-input" placeholder="Buscar nos manuais…" ' +
    'autocomplete="off" spellcheck="false" aria-label="Buscar nos manuais">' +
    '<span class="docsearch-key">/</span>';
  nav.insertBefore(box, nav.firstChild);

  var input = box.querySelector(".docsearch-input");
  var panel = document.createElement("div");
  panel.className = "docsearch-panel";
  panel.hidden = true;
  document.body.appendChild(panel);

  var active = -1;

  function close() { panel.hidden = true; active = -1; }

  function render(hits, query) {
    if (!query) { close(); return; }
    if (!hits.length) {
      panel.innerHTML = '<div class="docsearch-empty">Nada encontrado para <strong>' +
        esc(query) + "</strong>.</div>";
      panel.hidden = false;
      return;
    }
    // Agrupa por manual, preservando a ordem de relevância.
    var order = [], byDoc = {};
    hits.forEach(function (h) {
      if (!byDoc[h.sec.slug]) { byDoc[h.sec.slug] = []; order.push(h.sec.slug); }
      if (byDoc[h.sec.slug].length < 4) byDoc[h.sec.slug].push(h);
    });
    var html = '<div class="docsearch-count">' + hits.length +
      (hits.length === 1 ? " trecho" : " trechos") + " em " + order.length +
      (order.length === 1 ? " manual" : " manuais") + "</div>";
    order.forEach(function (slug) {
      var group = byDoc[slug], sec0 = group[0].sec;
      html += '<div class="docsearch-group"><div class="docsearch-doc">' +
        esc(sec0.docTitle) + '<span class="docsearch-area">' + esc(sec0.area) + "</span></div>";
      group.forEach(function (h) {
        var href = h.sec.slug + ".html" + (h.sec.anchor ? "#" + h.sec.anchor : "");
        html += '<a class="docsearch-hit" href="' + href + '">' +
          '<span class="docsearch-head">' + esc(h.sec.heading || "Início") + "</span>" +
          '<span class="docsearch-snip">' + snippet(h.sec, h.terms) + "</span></a>";
      });
      html += "</div>";
    });
    panel.innerHTML = html;
    panel.hidden = false;
    active = -1;
  }

  var timer = null;
  function run() {
    var q = input.value.trim();
    if (!q) { close(); return; }
    panel.innerHTML = '<div class="docsearch-empty">Procurando…</div>';
    panel.hidden = false;
    buildIndex().then(function () {
      if (input.value.trim() !== q) return;            // já digitou outra coisa
      render(search(q), q);
    });
  }

  input.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(run, 140);
  });
  input.addEventListener("focus", function () { buildIndex(); });

  input.addEventListener("keydown", function (e) {
    var hits = panel.querySelectorAll(".docsearch-hit");
    if (e.key === "Escape") { input.value = ""; close(); input.blur(); return; }
    if (!hits.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      active += e.key === "ArrowDown" ? 1 : -1;
      if (active < 0) active = hits.length - 1;
      if (active >= hits.length) active = 0;
      hits.forEach(function (h) { h.classList.remove("on"); });
      hits[active].classList.add("on");
      hits[active].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      hits[active].click();
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "/" || e.target === input) return;
    var tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || e.target.isContentEditable) return;
    e.preventDefault();
    input.focus();
    input.select();
  });

  document.addEventListener("click", function (e) {
    if (!panel.hidden && !panel.contains(e.target) && !box.contains(e.target)) close();
  });
})();
