/** @odoo-module **/

import { Component, markup, onMounted, onPatched, onWillStart, useRef, useState } from "@odoo/owl";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

// Links between pages point to the reader itself (/odoo/manuais/<id>, see
// URL_PAGINA in models/document_page.py); inside the reader they open in place.
const PAGE_LINK = /\/odoo\/manuais\/(\d+)(?:#(.+))?$/;

/** One node of the tree; recursive. */
export class ReaderNode extends Component {
    static template = "liber_knowledge.ReaderNode";
    static props = {
        node: Object,
        selectedId: { type: [Number, Boolean] },
        expanded: Object,
        onSelect: Function,
        onToggle: Function,
        depth: Number,
    };
    static components = {};

    get isOpen() {
        return !!this.props.expanded[this.props.node.id];
    }

    get isCategory() {
        return this.props.node.type === "category";
    }
}
ReaderNode.components = { ReaderNode };

/** The Manuals reader: tree on the left, the page on the right. */
export class KnowledgeReader extends Component {
    static template = "liber_knowledge.Reader";
    static components = { ReaderNode };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.contentRef = useRef("content");
        this.state = useState({
            tree: [],
            expanded: {},
            page: null,
            query: "",
            results: null,
            loading: true,
        });
        this.pendingAnchor = null;
        this.search = useDebounced(this.runSearch.bind(this), 250);

        onWillStart(async () => {
            this.state.tree = await this.orm.call("document.page", "liber_reader_tree", []);
            // Top-level categories start open: the reader lands on a map.
            for (const node of this.state.tree) {
                this.state.expanded[node.id] = true;
            }
            const startId = this.props.resId || this.props.action.context?.active_id;
            if (startId) {
                await this.loadPage(startId, { push: false });
            }
            this.state.loading = false;
        });
        onMounted(() => this.scrollToAnchor());
        onPatched(() => this.scrollToAnchor());
    }

    // -- navigation -------------------------------------------------------
    async loadPage(pageId, { anchor = null, push = true } = {}) {
        let page;
        try {
            page = await this.orm.call("document.page", "liber_reader_page", [[pageId]]);
        } catch {
            // deleted or not visible for this user: back to the map
            this.state.page = null;
            this.props.updateActionState?.({ resId: false });
            return;
        }
        page.content = markup(page.content || "");
        this.state.page = page;
        this.state.results = null;
        for (const step of page.path) {
            this.state.expanded[step.id] = true;
        }
        if (page.type === "category") {
            this.state.expanded[page.id] = true;
        }
        this.pendingAnchor = anchor || "__top__";
        if (push) {
            this.props.updateActionState?.({ resId: page.id });
        }
    }

    goHome() {
        this.state.page = null;
        this.state.results = null;
        this.state.query = "";
        this.pendingAnchor = "__top__";
        this.props.updateActionState?.({ resId: false });
    }

    onSelect(node) {
        this.loadPage(node.id);
    }

    onToggle(node) {
        this.state.expanded[node.id] = !this.state.expanded[node.id];
    }

    scrollToAnchor() {
        const anchor = this.pendingAnchor;
        const pane = this.contentRef.el;
        if (!anchor || !pane) {
            return;
        }
        this.pendingAnchor = null;
        if (anchor === "__top__") {
            pane.scrollTop = 0;
            return;
        }
        const target = pane.querySelector(`[id="${CSS.escape(anchor)}"]`);
        if (target) {
            target.scrollIntoView({ block: "start" });
        }
    }

    onContentClick(ev) {
        const link = ev.target.closest("a[href]");
        if (!link) {
            return;
        }
        const href = link.getAttribute("href");
        if (href.startsWith("#")) {
            ev.preventDefault();
            this.pendingAnchor = decodeURIComponent(href.slice(1));
            this.scrollToAnchor();
            return;
        }
        const match = href.match(PAGE_LINK);
        if (match) {
            ev.preventDefault();
            this.loadPage(parseInt(match[1]), { anchor: match[2] ? decodeURIComponent(match[2]) : null });
        }
    }

    // -- search -----------------------------------------------------------
    onSearchInput(ev) {
        this.state.query = ev.target.value;
        this.search();
    }

    async runSearch() {
        const query = this.state.query.trim();
        if (query.length < 2) {
            this.state.results = null;
            return;
        }
        this.state.results = await this.orm.call("document.page", "liber_reader_search", [query]);
    }

    clearSearch() {
        this.state.query = "";
        this.state.results = null;
    }

    // -- editing (editors only; the buttons are hidden for readers) --------
    openEditor() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "document.page",
            res_id: this.state.page.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    newPage() {
        const page = this.state.page;
        let parentId = false;
        if (page) {
            parentId = page.type === "category" ? page.id : page.path.at(-1)?.id || false;
        }
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "document.page",
            views: [[false, "form"]],
            target: "current",
            context: { default_type: "content", default_parent_id: parentId },
        });
    }

    get lastDate() {
        const value = this.state.page?.last_date;
        return value ? formatDateTime(deserializeDateTime(value)) : "";
    }

    get emptyText() {
        return _t("No page matches this search.");
    }
}

registry.category("actions").add("liber_knowledge.reader", KnowledgeReader);
