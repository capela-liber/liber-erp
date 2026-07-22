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
  { area: "Fiscal", desc: "Os XMLs das suas notas dentro do sistema — histórico, conferência e remessas.", items: [
    { slug: "liber_nfe_xml", title: "Importação de XML de NF-e", desc: "Importe as notas emitidas e recebidas e reconstrua o histórico." },
    { slug: "liber_nfe_remessa", title: "Notas de remessa", desc: "Documentos sem cobrança — consignação, bonificação, eventos." },
  ]},
  { area: "Catálogo", desc: "Metadados do livro entrando e saindo do sistema pelos padrões do mercado.", items: [
    { slug: "liber_metabooks_integration", title: "Integração Metabooks", desc: "Importação por ISBN, catálogo completo e envio ONIX." },
  ]},
  { area: "Divulgação", desc: "Exemplares de cortesia com dono, motivo e custo.", items: [
    { slug: "liber_product_bonus", title: "Bonificação", desc: "Campanhas, listas de destinatários e custo por título." },
  ]},
  { area: "Arquivos", desc: "O acervo da editora no Dropbox, com o Odoo de porteiro.", items: [
    { slug: "liber_dropbox", title: "Arquivos no Dropbox", desc: "Leitura e escrita por pasta, envio, links com prazo e vínculos a autores e títulos." },
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
