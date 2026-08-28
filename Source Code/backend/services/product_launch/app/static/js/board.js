/* =========================================================================
   ProductBoard — the products table + add/edit/delete modal, shared by the
   client page and the admin review page. Talks to the token-gated API.
   ========================================================================= */
(function () {
  const el = window.UI.el;
  const toast = window.UI.toast;

  class ProductBoard {
    constructor(token) {
      this.token = token;
      this.base = `/api/launch/${encodeURIComponent(token)}`;
      this.state = { launch: null, config: null, products: [], summary: null };
      this.form = null;
      this.editingPid = null;
      this._changeCbs = [];

      // DOM
      this.tbody = document.getElementById("products-tbody");
      this.table = document.getElementById("products-table");
      this.emptyBox = document.getElementById("products-empty");
      this.progressBar = document.getElementById("progress-bar");
      this.progressText = document.getElementById("progress-text");

      this.modal = document.getElementById("product-modal");
      this.formHost = document.getElementById("product-form");
      this.modalTitle = document.getElementById("modal-title");
      this.saveBtn = document.getElementById("save-product-btn");
      this.deleteBtn = document.getElementById("delete-product-btn");

      this._wire();
    }

    onChange(cb) { this._changeCbs.push(cb); }
    _emit() { this._changeCbs.forEach((cb) => cb(this.state)); }

    _wire() {
      const addBtn = document.getElementById("add-product-btn");
      if (addBtn) addBtn.addEventListener("click", () => this.openCreate());
      const addBtn2 = document.getElementById("add-product-empty-btn");
      if (addBtn2) addBtn2.addEventListener("click", () => this.openCreate());

      document.querySelectorAll("[data-close-modal]").forEach((b) =>
        b.addEventListener("click", () => this.closeModal()));
      if (this.modal) this.modal.addEventListener("click", (e) => {
        if (e.target === this.modal) this.closeModal();
      });
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && this.modal && this.modal.classList.contains("open")) this.closeModal();
      });

      if (this.saveBtn) this.saveBtn.addEventListener("click", () => this.save());
      if (this.deleteBtn) this.deleteBtn.addEventListener("click", () => this.deleteCurrent());
    }

    async load() {
      const data = await window.API.get(this.base);
      this._ingest(data);
    }

    _ingest(data) {
      this.state.launch = data.launch;
      this.state.config = data.config;
      this.state.products = data.products;
      this.state.summary = data.summary;
      if (!this.form) this.form = new window.ProductForm(this.formHost, data.config);
      this.renderTable();
      this.renderProgress();
      this._emit();
    }

    // ---------- table ----------
    _cellText(field, value) {
      if (Array.isArray(value)) return value.join(", ");
      return value == null ? "" : String(value);
    }

    _priceRange(items) {
      const nums = (items || [])
        .map((it) => parseFloat(String(it.price || "").replace(/,/g, "")))
        .filter((n) => !isNaN(n));
      if (!nums.length) return "—";
      const fmt = (n) => n.toLocaleString();
      const lo = Math.min(...nums), hi = Math.max(...nums);
      return lo === hi ? fmt(lo) : `${fmt(lo)}–${fmt(hi)}`;
    }

    _itemSummary(items) {
      if (!items || !items.length) return "—";
      const names = items.map((it) => it.item).filter(Boolean);
      const label = names.length ? names.join(", ") : `${items.length} set(s)`;
      return `${items.length} · ${label}`;
    }

    renderTable() {
      const cfg = this.state.config;
      const cols = cfg.table_columns || [];
      const fmap = {};
      (cfg.product_fields || []).forEach((f) => (fmap[f.key] = f));
      const itemLabel = cfg.item_label || "Item-set";

      // header (built once from config)
      const thead = this.table.querySelector("thead tr");
      if (thead && !thead.dataset.built) {
        thead.appendChild(el("th", { text: "#" }));
        cols.forEach((k) => thead.appendChild(el("th", { text: (fmap[k] || {}).label || k })));
        thead.appendChild(el("th", { text: itemLabel + "s" }));
        thead.appendChild(el("th", { text: "Price" }));
        thead.appendChild(el("th", { text: "Status" }));
        thead.appendChild(el("th", { class: "actions", text: "Actions" }));
        thead.dataset.built = "1";
      }

      this.tbody.innerHTML = "";
      if (!this.state.products.length) {
        this.table.style.display = "none";
        if (this.emptyBox) this.emptyBox.style.display = "";
        return;
      }
      this.table.style.display = "";
      if (this.emptyBox) this.emptyBox.style.display = "none";

      this.state.products.forEach((p, idx) => {
        const prod = (p.data && p.data.product) || {};
        const items = (p.data && p.data.items) || [];
        const tr = el("tr");
        tr.appendChild(el("td", { class: "muted", "data-label": "No.", text: String(idx + 1) }));
        cols.forEach((k) => {
          const td = el("td", { "data-label": (fmap[k] || {}).label || k });
          const txt = this._cellText(fmap[k], prod[k]);
          if (k === cfg.title_field) td.className = "cell-title";
          td.appendChild(el("div", { class: "truncate", text: txt || "—", title: txt }));
          tr.appendChild(td);
        });
        const itemsTxt = this._itemSummary(items);
        tr.appendChild(el("td", { "data-label": itemLabel + "s" },
          [el("div", { class: "truncate", text: itemsTxt, title: itemsTxt })]));
        tr.appendChild(el("td", { "data-label": "Price", text: this._priceRange(items) }));
        tr.appendChild(el("td", { "data-label": "Status" }, [this._statusBadge(p)]));

        const actions = el("td", { class: "actions" }, [
          el("button", { class: "btn btn-sm", onclick: () => this.openEdit(p.pid) }, "Edit"),
          el("button", { class: "btn btn-sm btn-danger", onclick: () => this.deletePid(p.pid) }, "Delete"),
        ]);
        tr.appendChild(actions);
        this.tbody.appendChild(tr);
      });
    }

    _issueCount(v) {
      let n = (v.missing || []).length + Object.keys(v.product_errors || {}).length;
      (v.item_errors || []).forEach((e) => (n += Object.keys(e || {}).length));
      return n;
    }

    _statusBadge(p) {
      const v = p.validation || {};
      if (v.complete)
        return el("span", { class: "badge badge-ok badge-dot", text: "Complete" });
      if (p.duplicate_sku)
        return el("span", { class: "badge badge-danger badge-dot", text: "Duplicate SKU", title: (v.missing || []).join(", ") });
      const n = this._issueCount(v);
      return el("span", {
        class: "badge badge-warn badge-dot",
        text: `${n} field${n === 1 ? "" : "s"} to fix`,
        title: (v.missing || []).join(", "),
      });
    }

    renderProgress() {
      const s = this.state.summary;
      if (!s) return;
      const pct = s.total ? Math.round((s.complete / s.total) * 100) : 0;
      if (this.progressBar) this.progressBar.style.width = pct + "%";
      if (this.progressText)
        this.progressText.textContent =
          `${s.complete} of ${s.total} product${s.total === 1 ? "" : "s"} complete`;
    }

    // ---------- modal ----------
    openCreate() {
      this.editingPid = null;
      this.modalTitle.textContent = "Add Product";
      this.form.render();
      this.form.setValues({ product: {}, items: [] });
      if (this.deleteBtn) this.deleteBtn.style.display = "none";
      this._openModal();
    }

    openEdit(pid) {
      const p = this.state.products.find((x) => x.pid === pid);
      if (!p) return;
      this.editingPid = pid;
      this.modalTitle.textContent = "Edit Product";
      this.form.render();
      this.form.setValues(p.data);
      this.form.showValidation(p.validation);
      if (this.deleteBtn) this.deleteBtn.style.display = "";
      this._openModal();
    }

    _openModal() {
      this.modal.classList.add("open");
      document.body.style.overflow = "hidden";
      const first = this.formHost.querySelector("input, textarea, select");
      if (first) setTimeout(() => first.focus(), 40);
    }
    closeModal() {
      this.modal.classList.remove("open");
      document.body.style.overflow = "";
    }

    async save() {
      const data = this.form.getValues();
      this.saveBtn.disabled = true;
      const original = this.saveBtn.textContent;
      this.saveBtn.textContent = "Saving…";
      try {
        let resp;
        if (this.editingPid) {
          resp = await window.API.put(`${this.base}/products/${this.editingPid}`, { data });
        } else {
          resp = await window.API.post(`${this.base}/products`, { data });
        }
        this._ingest(resp);
        toast(this.editingPid ? "Product updated." : "Product added.", "ok");
        this.closeModal();
      } catch (err) {
        toast(err.message || "Could not save.", "err");
      } finally {
        this.saveBtn.disabled = false;
        this.saveBtn.textContent = original;
      }
    }

    deleteCurrent() { if (this.editingPid) this.deletePid(this.editingPid, true); }

    async deletePid(pid, closeAfter = false) {
      const p = this.state.products.find((x) => x.pid === pid);
      const name = (p && p.data.product && p.data.product[this.state.config.title_field]) || "this product";
      if (!window.confirm(`Delete “${name}”? This cannot be undone.`)) return;
      try {
        const resp = await window.API.del(`${this.base}/products/${pid}`);
        this._ingest(resp);
        toast("Product deleted.", "ok");
        if (closeAfter) this.closeModal();
      } catch (err) {
        toast(err.message || "Could not delete.", "err");
      }
    }
  }

  window.ProductBoard = ProductBoard;
})();
