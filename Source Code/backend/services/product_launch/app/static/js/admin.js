/* Admin controller: handles both the dashboard (list/create/delete/status)
   and the launch review page (board in admin mode + status + export). */
(function () {
  const el = window.UI.el, toast = window.UI.toast;
  const page = document.body.dataset.adminPage;

  async function copy(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
      if (btn) { const t = btn.textContent; btn.textContent = "Copied!"; setTimeout(() => (btn.textContent = t), 1200); }
      else toast("Copied to clipboard.", "ok");
    } catch (e) {
      window.prompt("Copy this link:", text);
    }
  }
  window.__copy = copy;

  // ---------------- dashboard ----------------
  if (page === "dashboard") {
    const modal = document.getElementById("new-launch-modal");
    const openBtn = document.getElementById("new-launch-btn");
    const createBtn = document.getElementById("create-launch-btn");
    const resultBox = document.getElementById("new-launch-result");
    const formBox = document.getElementById("new-launch-form");

    const open = () => { modal.classList.add("open"); document.body.style.overflow = "hidden"; };
    const close = () => { modal.classList.remove("open"); document.body.style.overflow = ""; resetModal(); };
    function resetModal() {
      formBox.style.display = ""; resultBox.style.display = "none";
      document.getElementById("nl-brand").value = "";
      document.getElementById("nl-contact").value = "";
      document.getElementById("nl-email").value = "";
    }
    if (openBtn) openBtn.addEventListener("click", () => { resetModal(); open(); });
    document.querySelectorAll("[data-close-nl]").forEach((b) => b.addEventListener("click", close));
    if (modal) modal.addEventListener("click", (e) => { if (e.target === modal) close(); });

    if (createBtn) createBtn.addEventListener("click", async () => {
      const brand = document.getElementById("nl-brand").value.trim();
      if (!brand) { toast("Please enter a brand name.", "err"); return; }
      createBtn.disabled = true;
      try {
        const resp = await window.API.post("/admin/api/launches", {
          brand_name: brand,
          contact_name: document.getElementById("nl-contact").value.trim(),
          contact_email: document.getElementById("nl-email").value.trim(),
        });
        formBox.style.display = "none";
        resultBox.style.display = "";
        document.getElementById("nl-client-url").value = resp.client_url;
        const openReview = document.getElementById("nl-open-review");
        openReview.href = resp.review_url;
      } catch (e) { toast(e.message || "Could not create.", "err"); }
      finally { createBtn.disabled = false; }
    });

    document.querySelectorAll("[data-copy]").forEach((b) =>
      b.addEventListener("click", () => copy(b.dataset.copy, b)));

    const nlCopy = document.getElementById("nl-copy-btn");
    if (nlCopy) nlCopy.addEventListener("click", () => copy(document.getElementById("nl-client-url").value, nlCopy));

    // status change + delete per row
    document.querySelectorAll("select[data-status-token]").forEach((sel) => {
      sel.addEventListener("change", async () => {
        try {
          await window.API.put(`/admin/api/launch/${sel.dataset.statusToken}/status`, { status: sel.value });
          toast("Status updated.", "ok");
          const pill = document.querySelector(`[data-status-pill="${sel.dataset.statusToken}"]`);
          if (pill) { pill.textContent = sel.value; pill.className = "status-pill status-" + sel.value.replace(/\s+/g, "-"); }
        } catch (e) { toast("Could not update status.", "err"); }
      });
    });
    document.querySelectorAll("[data-delete-token]").forEach((b) =>
      b.addEventListener("click", async () => {
        if (!window.confirm(`Delete launch for “${b.dataset.brand}”? All its products will be removed.`)) return;
        try {
          await window.API.del(`/admin/api/launch/${b.dataset.deleteToken}`);
          const tr = b.closest("tr"); if (tr) tr.remove();
          toast("Launch deleted.", "ok");
        } catch (e) { toast("Could not delete.", "err"); }
      }));
  }

  // ---------------- review page ----------------
  if (page === "review") {
    const token = window.LAUNCH_TOKEN;
    const board = new window.ProductBoard(token);

    board.onChange((state) => {
      const c = document.getElementById("meta-product-count");
      if (c) c.textContent = state.summary.total;
      const cc = document.getElementById("meta-complete-count");
      if (cc) cc.textContent = `${state.summary.complete} / ${state.summary.total}`;
      const upd = document.getElementById("meta-updated");
      if (upd && state.launch.updated_at) upd.textContent = new Date(state.launch.updated_at).toLocaleString();
    });

    const statusSel = document.getElementById("admin-status");
    if (statusSel) statusSel.addEventListener("change", async () => {
      try {
        await window.API.put(`/admin/api/launch/${token}/status`, { status: statusSel.value });
        const pill = document.getElementById("status-pill");
        if (pill) { pill.textContent = statusSel.value; pill.className = "status-pill status-" + statusSel.value.replace(/\s+/g, "-"); }
        toast("Status updated.", "ok");
      } catch (e) { toast("Could not update status.", "err"); }
    });

    document.querySelectorAll("[data-copy]").forEach((b) =>
      b.addEventListener("click", () => copy(b.dataset.copy, b)));

    board.load().catch(() => toast("Could not load launch.", "err"));
  }
})();
