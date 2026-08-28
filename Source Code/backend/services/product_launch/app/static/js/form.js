/* =========================================================================
   Dynamic form building from the field config (two-level model):
     • FormRenderer  — renders one flat set of fields into a container.
     • ProductForm   — product-level fields + a repeatable list of item-sets,
                       each item-set being its own FormRenderer.
   Also exposes small UI helpers (el, toast) on window.UI.
   ========================================================================= */
(function () {
  const el = (tag, attrs = {}, children = []) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
      else if (v !== null && v !== undefined) node.setAttribute(k, v);
    }
    (Array.isArray(children) ? children : [children]).forEach((c) => {
      if (c == null) return;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  };

  const SPAN2 = new Set(["textarea", "tags", "multiselect"]);

  function toast(message, kind = "") {
    let box = document.querySelector(".toasts");
    if (!box) { box = el("div", { class: "toasts" }); document.body.appendChild(box); }
    const t = el("div", { class: "toast " + kind, text: message });
    box.appendChild(t);
    setTimeout(() => { t.style.opacity = "0"; setTimeout(() => t.remove(), 250); }, 2800);
  }

  window.UI = { el, toast };

  // ---------------------------------------------------------------- //
  // FormRenderer — one flat fieldset
  // ---------------------------------------------------------------- //
  class FormRenderer {
    constructor(container, fields, { groups = null, idPrefix = "" } = {}) {
      this.container = container;
      this.fields = fields || [];
      this.groups = groups;
      this.idPrefix = idPrefix;
      this.inputs = {};
    }

    render() {
      this.container.innerHTML = "";
      this.inputs = {};
      const grid = el("div", { class: "form-grid" });

      if (this.groups && this.groups.length) {
        const seen = new Set();
        this.groups.forEach((group) => {
          const gf = this.fields.filter((f) => (f.group || "") === group.id);
          if (!gf.length) return;
          if (group.label) grid.appendChild(el("div", { class: "fieldset-title", text: group.label }));
          gf.forEach((f) => { seen.add(f.key); grid.appendChild(this._fieldNode(f)); });
        });
        const leftover = this.fields.filter((f) => !seen.has(f.key));
        if (leftover.length) {
          grid.appendChild(el("div", { class: "fieldset-title", text: "Other" }));
          leftover.forEach((f) => grid.appendChild(this._fieldNode(f)));
        }
      } else {
        this.fields.forEach((f) => grid.appendChild(this._fieldNode(f)));
      }

      this.container.appendChild(grid);
      return this;
    }

    _id(key) { return this.idPrefix + "f_" + key; }

    _fieldNode(field) {
      const group = el("div", { class: "form-group" + (SPAN2.has(field.type) ? " span-2" : "") });
      const label = el("label", { class: "field-label", text: field.label, for: this._id(field.key) });
      if (field.required) label.appendChild(el("span", { class: "req", text: "*" }));
      group.appendChild(label);

      const control = (this["_type_" + field.type] || this._type_text).call(this, field);
      group.appendChild(control.node);
      if (field.help) group.appendChild(el("div", { class: "field-help", text: field.help }));
      const errNode = el("div", { class: "field-error", style: "display:none" });
      group.appendChild(errNode);

      this.inputs[field.key] = {
        get: control.get,
        set: control.set,
        setError: (msg) => { errNode.textContent = msg; errNode.style.display = ""; control.markInvalid && control.markInvalid(true); },
        clearError: () => { errNode.textContent = ""; errNode.style.display = "none"; control.markInvalid && control.markInvalid(false); },
      };
      return group;
    }

    _type_text(field, inputType = "text") {
      const input = el("input", { type: inputType, id: this._id(field.key), placeholder: field.placeholder || "" });
      let node = input;
      if (field.prefix) node = el("div", { class: "input-prefix" }, [el("span", { class: "pfx", text: field.prefix }), input]);
      return { node, get: () => input.value, set: (v) => { input.value = v == null ? "" : v; }, markInvalid: (b) => input.classList.toggle("input-invalid", b) };
    }
    _type_email(field) { return this._type_text(field, "email"); }
    _type_url(field) { return this._type_text(field, "url"); }
    _type_number(field) {
      const c = this._type_text(field, "number");
      const input = c.node.querySelector ? c.node.querySelector("input") : c.node;
      if (field.min !== undefined) input.setAttribute("min", field.min);
      input.setAttribute("step", "any");
      return c;
    }
    _type_textarea(field) {
      const ta = el("textarea", { id: this._id(field.key), placeholder: field.placeholder || "" });
      return { node: ta, get: () => ta.value, set: (v) => { ta.value = v == null ? "" : v; }, markInvalid: (b) => ta.classList.toggle("input-invalid", b) };
    }
    _type_select(field) {
      const sel = el("select", { id: this._id(field.key) });
      sel.appendChild(el("option", { value: "", text: field.placeholder || "— Select —" }));
      (field.options || []).forEach((o) => sel.appendChild(el("option", { value: o, text: o })));
      return { node: sel, get: () => sel.value, set: (v) => { sel.value = v == null ? "" : v; }, markInvalid: (b) => sel.classList.toggle("input-invalid", b) };
    }
    _type_multiselect(field) {
      const wrap = el("div", { class: "chips" });
      const state = new Set();
      (field.options || []).forEach((o) => {
        const chip = el("div", { class: "chip-opt", text: o, role: "button", tabindex: "0" });
        const toggle = () => { state.has(o) ? (state.delete(o), chip.classList.remove("active")) : (state.add(o), chip.classList.add("active")); };
        chip.addEventListener("click", toggle);
        chip.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
        wrap.appendChild(chip);
      });
      return {
        node: wrap,
        get: () => (field.options || []).filter((o) => state.has(o)),
        set: (arr) => { state.clear(); (arr || []).forEach((v) => state.add(v)); [...wrap.children].forEach((c) => c.classList.toggle("active", state.has(c.textContent))); },
        markInvalid: (b) => wrap.classList.toggle("input-invalid", b),
      };
    }
    _type_tags(field) {
      const values = [];
      const box = el("div", { class: "tags-input" });
      const input = el("input", { type: field.subtype === "url" ? "url" : "text", placeholder: "Type and press Enter…" });
      const renderTags = () => {
        [...box.querySelectorAll(".tag")].forEach((n) => n.remove());
        values.forEach((v, i) => {
          const tag = el("span", { class: "tag" }, [el("span", { text: v }), el("button", { type: "button", text: "×", title: "Remove", onclick: () => { values.splice(i, 1); renderTags(); } })]);
          box.insertBefore(tag, input);
        });
      };
      const add = (raw) => { raw.split(",").map((s) => s.trim()).filter(Boolean).forEach((v) => { if (!values.includes(v)) values.push(v); }); input.value = ""; renderTags(); };
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === ",") { e.preventDefault(); if (input.value.trim()) add(input.value); }
        else if (e.key === "Backspace" && !input.value && values.length) { values.pop(); renderTags(); }
      });
      input.addEventListener("blur", () => { if (input.value.trim()) add(input.value); });
      box.addEventListener("click", () => input.focus());
      box.appendChild(input);
      return { node: box, get: () => values.slice(), set: (arr) => { values.length = 0; (arr || []).forEach((v) => values.push(v)); renderTags(); }, markInvalid: (b) => box.classList.toggle("input-invalid", b) };
    }

    getValues() { const o = {}; for (const [k, c] of Object.entries(this.inputs)) o[k] = c.get(); return o; }
    setValues(data) { data = data || {}; for (const [k, c] of Object.entries(this.inputs)) c.set(data[k]); }
    clearErrors() { Object.values(this.inputs).forEach((c) => c.clearError()); }
    showErrors(errors) { this.clearErrors(); for (const [k, m] of Object.entries(errors || {})) if (this.inputs[k]) this.inputs[k].setError(m); }
  }

  // ---------------------------------------------------------------- //
  // ProductForm — product fields + repeatable item-sets
  // ---------------------------------------------------------------- //
  class ProductForm {
    constructor(host, config) {
      this.host = host;
      this.config = config;
      this.productRenderer = null;
      this.itemSets = []; // [{ renderer, card }]
    }

    render() {
      this.host.innerHTML = "";
      this.itemSets = [];

      // product-level
      const prodHost = el("div");
      this.host.appendChild(prodHost);
      this.productRenderer = new FormRenderer(prodHost, this.config.product_fields, {
        groups: this.config.groups, idPrefix: "p_",
      });
      this.productRenderer.render();

      // item-sets section
      const label = this.config.item_label || "Item-set";
      this.host.appendChild(el("div", { class: "itemsets-title" }, [
        el("span", { text: label + "s" }),
        el("span", { class: "field-help", text: "Add one for each priced option (e.g. 2-piece, 3-piece)." }),
      ]));
      this.itemsHost = el("div", { class: "itemsets" });
      this.host.appendChild(this.itemsHost);

      this.addBtn = el("button", {
        type: "button", class: "btn btn-sm add-itemset",
        text: "＋ Add " + label.toLowerCase(),
        onclick: () => this.addItemSet(),
      });
      this.host.appendChild(this.addBtn);
      return this;
    }

    addItemSet(values) {
      const idx = this.itemSets.length;
      const label = this.config.item_label || "Item-set";
      const body = el("div");
      const head = el("div", { class: "itemset-head" }, [
        el("strong", { class: "itemset-name" }, [
          el("span", { class: "num", text: String(idx + 1) }),
          el("span", { class: "itemset-word", text: label }),
        ]),
        el("button", { type: "button", class: "btn btn-sm btn-danger", text: "Remove", onclick: () => this.removeItemSet(card) }),
      ]);
      const card = el("div", { class: "itemset-card" }, [head, body]);
      this.itemsHost.appendChild(card);

      const renderer = new FormRenderer(body, this.config.item_fields, { idPrefix: `i${idx}_${Date.now()}_` });
      renderer.render();
      if (values) renderer.setValues(values);
      this.itemSets.push({ renderer, card });
      this._renumber();
      return renderer;
    }

    removeItemSet(card) {
      const i = this.itemSets.findIndex((s) => s.card === card);
      if (i === -1) return;
      card.remove();
      this.itemSets.splice(i, 1);
      this._renumber();
    }

    _renumber() {
      const label = this.config.item_label || "Item-set";
      this.itemSets.forEach((s, i) => {
        const numEl = s.card.querySelector(".itemset-name .num");
        if (numEl) numEl.textContent = String(i + 1);
        const wordEl = s.card.querySelector(".itemset-name .itemset-word");
        if (wordEl) wordEl.textContent = label;
      });
    }

    getValues() {
      return {
        product: this.productRenderer.getValues(),
        items: this.itemSets.map((s) => s.renderer.getValues()),
      };
    }

    setValues(data) {
      data = data || {};
      this.productRenderer.setValues(data.product || {});
      // reset item-sets
      this.itemsHost.innerHTML = "";
      this.itemSets = [];
      const items = data.items || [];
      if (items.length) items.forEach((it) => this.addItemSet(it));
      else {
        const min = this.config.min_items || 1;
        for (let i = 0; i < min; i++) this.addItemSet({});
      }
    }

    clearErrors() {
      this.productRenderer.clearErrors();
      this.itemSets.forEach((s) => s.renderer.clearErrors());
    }

    showValidation(v) {
      this.clearErrors();
      if (!v) return;
      this.productRenderer.showErrors(v.product_errors || {});
      (v.item_errors || []).forEach((errs, i) => {
        if (this.itemSets[i]) this.itemSets[i].renderer.showErrors(errs);
      });
    }
  }

  window.FormRenderer = FormRenderer;
  window.ProductForm = ProductForm;
})();
