/* Client page controller: boots the board, autosaves brand/contact,
   drives the "Review & Submit" summary. */
(function () {
  const token = window.LAUNCH_TOKEN;
  if (!token) return;
  const el = window.UI.el, toast = window.UI.toast;

  const board = new window.ProductBoard(token);
  const base = `/api/launch/${encodeURIComponent(token)}`;

  const brandInput = document.getElementById("brand-name");
  const contactName = document.getElementById("contact-name");
  const contactEmail = document.getElementById("contact-email");
  const appbarBrand = document.getElementById("appbar-brand");
  const statusPill = document.getElementById("status-pill");
  const saveDot = document.getElementById("save-indicator");
  const submitBtn = document.getElementById("submit-btn");

  function setSaving(state) {
    if (!saveDot) return;
    saveDot.className = "save-dot" + (state === "saving" ? " saving" : state === "error" ? " error" : "");
    saveDot.querySelector(".label").textContent =
      state === "saving" ? "Saving…" : state === "error" ? "Not saved" : "All changes saved";
  }

  board.onChange((state) => {
    const ln = state.launch;
    if (appbarBrand) appbarBrand.textContent = ln.brand_name || "Untitled brand";
    if (statusPill) { statusPill.textContent = ln.status; statusPill.className = "status-pill status-" + ln.status.replace(/\s+/g, "-"); }
    if (brandInput && document.activeElement !== brandInput) brandInput.value = ln.brand_name || "";
    if (contactName && document.activeElement !== contactName) contactName.value = ln.contact_name || "";
    if (contactEmail && document.activeElement !== contactEmail) contactEmail.value = ln.contact_email || "";
  });

  let saveTimer = null;
  async function saveMeta() {
    setSaving("saving");
    try {
      await window.API.put(base, {
        brand_name: brandInput ? brandInput.value : "",
        contact_name: contactName ? contactName.value : "",
        contact_email: contactEmail ? contactEmail.value : "",
      });
      setSaving("saved");
      if (appbarBrand && brandInput) appbarBrand.textContent = brandInput.value || "Untitled brand";
    } catch (e) {
      setSaving("error");
      toast("Could not save details.", "err");
    }
  }
  [brandInput, contactName, contactEmail].forEach((inp) => {
    if (!inp) return;
    inp.addEventListener("input", () => { setSaving("saving"); clearTimeout(saveTimer); saveTimer = setTimeout(saveMeta, 700); });
    inp.addEventListener("blur", () => { clearTimeout(saveTimer); saveMeta(); });
  });

  // ----- submit flow -----
  const submitModal = document.getElementById("submit-modal");
  const submitSummary = document.getElementById("submit-summary");
  const confirmBtn = document.getElementById("confirm-submit-btn");

  function openSubmit() {
    const s = board.state;
    submitSummary.innerHTML = "";
    if (!s.products.length) {
      submitSummary.appendChild(el("p", { class: "muted", text: "You haven't added any products yet." }));
    } else {
      const incomplete = s.products.filter((p) => !p.validation.complete || p.duplicate_sku);
      if (!incomplete.length) {
        submitSummary.appendChild(el("p", {
          class: "badge badge-ok badge-dot",
          text: `All ${s.products.length} products are complete.`,
        }));
      } else {
        submitSummary.appendChild(el("p", { class: "small", text:
          `${incomplete.length} of ${s.products.length} products still need attention. You can still submit — we'll follow up on anything missing.` }));
        const ul = el("ul", { class: "summary-list" });
        incomplete.forEach((p, i) => {
          const prod = (p.data && p.data.product) || {};
          const name = prod[s.config.title_field] || `Product ${i + 1}`;
          const numeric = [
            ...Object.values(p.validation.product_errors || {}),
            ...(p.validation.item_errors || []).flatMap((e) => Object.values(e || {})),
          ];
          const issues = [...(p.validation.missing || []), ...numeric];
          ul.appendChild(el("li", {}, [
            el("strong", { text: name }),
            el("span", { class: "muted small", text: issues.join(", ") || "Incomplete" }),
          ]));
        });
        submitSummary.appendChild(ul);
      }
    }
    submitModal.classList.add("open");
    document.body.style.overflow = "hidden";
  }
  function closeSubmit() { submitModal.classList.remove("open"); document.body.style.overflow = ""; }

  if (submitBtn) submitBtn.addEventListener("click", openSubmit);
  document.querySelectorAll("[data-close-submit]").forEach((b) => b.addEventListener("click", closeSubmit));
  if (submitModal) submitModal.addEventListener("click", (e) => { if (e.target === submitModal) closeSubmit(); });
  if (confirmBtn) confirmBtn.addEventListener("click", async () => {
    confirmBtn.disabled = true;
    try {
      const resp = await window.API.post(`${base}/submit`);
      board._ingest(resp);
      toast("Submitted. Thank you!", "ok");
      closeSubmit();
    } catch (e) { toast("Could not submit.", "err"); }
    finally { confirmBtn.disabled = false; }
  });

  board.load().catch(() => toast("Could not load this launch.", "err"));
})();
