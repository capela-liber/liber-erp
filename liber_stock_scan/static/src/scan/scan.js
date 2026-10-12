/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const ZXING = "/liber_stock_scan/static/lib/zxing/zxing.umd.js";

/**
 * A tela de bipagem: um campo, três passos.
 *
 * O passo não é um botão: é o que entra no campo. Prateleira abre a origem
 * (ou troca a origem, se nenhum livro foi bipado ainda; ou fecha como
 * destino, se já há livros). Livro soma uma linha. O servidor
 * (liber.shelf.scan) diz o que o código é; a tela só decide o passo.
 */
export class ShelfScan extends Component {
    static template = "liber_stock_scan.Scan";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.inputRef = useRef("input");
        this.videoRef = useRef("video");
        this.state = useState({
            origin: null,       // {id, name, complete_name, warehouse}
            lines: [],          // [{product_id, name, barcode, qty, on_hand}]
            message: "",        // aviso da última leitura
            messageKind: "",    // "error" | "ok"
            last: null,         // {name, qty, origin, dest} da última transferência
            busy: false,
            camera: false,
        });
        this.reader = null;
        this.lastCameraCode = { code: "", at: 0 };
        onMounted(() => this.focus());
        onWillUnmount(() => this.stopCamera());
    }

    // -- o passo atual ----------------------------------------------------

    get step() {
        if (!this.state.origin) {
            return "origin";
        }
        return this.state.lines.length ? "dest" : "books";
    }

    get total() {
        return this.state.lines.reduce((s, l) => s + l.qty, 0);
    }

    get hint() {
        return {
            origin: _t("Scan the shelf the books leave from"),
            books: _t("Scan the books, one by one"),
            dest: _t("Scan more books, or the destination shelf to finish"),
        }[this.step];
    }

    focus() {
        this.inputRef.el && this.inputRef.el.focus();
    }

    say(message, kind = "error") {
        this.state.message = message;
        this.state.messageKind = kind;
    }

    // -- entrada ------------------------------------------------------------

    onKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        ev.preventDefault();
        const code = ev.target.value.trim();
        ev.target.value = "";
        if (code) {
            this.handle(code);
        }
    }

    async handle(code) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const originId = this.state.origin ? this.state.origin.id : false;
            const r = await this.orm.call("liber.shelf.scan", "scan", [code, originId]);
            if (r.kind === "error") {
                this.say(r.message);
            } else if (r.kind === "location") {
                await this.onLocation(r);
            } else if (r.kind === "product") {
                this.onProduct(r);
            }
        } catch (e) {
            this.say(this.errorText(e));
        } finally {
            this.state.busy = false;
            this.focus();
        }
    }

    errorText(e) {
        return (e && e.data && e.data.message) || (e && e.message) || String(e);
    }

    async onLocation(loc) {
        if (!this.state.origin || !this.state.lines.length) {
            // Primeira prateleira, ou troca antes de qualquer livro.
            this.state.origin = loc;
            this.state.last = null;
            this.say(_t("Origin: %s", loc.name), "ok");
            return;
        }
        if (loc.id === this.state.origin.id) {
            this.say(_t("%s is the origin shelf; scan the destination shelf.", loc.name));
            return;
        }
        await this.transfer(loc);
    }

    onProduct(prod) {
        if (!this.state.origin) {
            this.say(_t("Scan the origin shelf first."));
            return;
        }
        const line = this.state.lines.find((l) => l.product_id === prod.id);
        const already = line ? line.qty : 0;
        if (already + 1 > prod.on_hand) {
            this.say(_t("%(product)s: only %(qty)s on %(shelf)s.", {
                product: prod.name, qty: prod.on_hand, shelf: this.state.origin.name,
            }));
            return;
        }
        if (line) {
            line.qty += 1;
        } else {
            this.state.lines.push({
                product_id: prod.id, name: prod.name, barcode: prod.barcode,
                qty: 1, on_hand: prod.on_hand,
            });
        }
        this.say(_t("%(product)s: %(qty)s", { product: prod.name, qty: already + 1 }), "ok");
    }

    async transfer(dest) {
        const lines = this.state.lines.map((l) => ({ product_id: l.product_id, qty: l.qty }));
        const r = await this.orm.call("liber.shelf.scan", "transfer", [
            this.state.origin.id, dest.id, lines,
        ]);
        this.state.last = r;
        this.state.origin = null;
        this.state.lines = [];
        this.say(_t("%(name)s done: %(qty)s from %(origin)s to %(dest)s.", r), "ok");
    }

    // -- botões ----------------------------------------------------------------

    undo() {
        const line = this.state.lines[this.state.lines.length - 1];
        if (!line) {
            return;
        }
        line.qty -= 1;
        if (line.qty <= 0) {
            this.state.lines.pop();
        }
        this.say(_t("Undone: %s", line.name), "ok");
        this.focus();
    }

    reset() {
        this.state.origin = null;
        this.state.lines = [];
        this.say("", "ok");
        this.focus();
    }

    // -- câmera -------------------------------------------------------------------

    async toggleCamera() {
        if (this.state.camera) {
            this.stopCamera();
            return;
        }
        try {
            await loadJS(ZXING);
            const ZX = window.ZXing;
            this.reader = new ZX.BrowserMultiFormatReader();
            const video = this.videoRef.el;
            // Sem o elemento, o ZXing cria um <video> solto e a câmera lê
            // por baixo de um quadro preto: melhor recusar e dizer.
            if (!video) {
                throw new Error(_t("the video area is missing"));
            }
            this.state.camera = true;
            await this.reader.decodeFromVideoDevice(undefined, video, (result) => {
                if (!result) {
                    return;
                }
                const code = result.getText();
                const now = Date.now();
                // O mesmo código lido em sequência pela câmera é um bipe só.
                if (code === this.lastCameraCode.code && now - this.lastCameraCode.at < 1500) {
                    return;
                }
                this.lastCameraCode = { code, at: now };
                this.handle(code);
            });
        } catch (e) {
            this.state.camera = false;
            this.say(_t("Camera unavailable: %s", this.errorText(e)));
        }
    }

    stopCamera() {
        if (this.reader) {
            try {
                this.reader.reset();
            } catch (e) {
                // já parada
            }
            this.reader = null;
        }
        this.state.camera = false;
        this.focus();
    }
}

registry.category("actions").add("liber_stock_scan.scan", ShelfScan);
