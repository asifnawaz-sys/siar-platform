/* Tiny fetch wrapper: JSON in/out, CSRF header for admin writes, uniform errors. */
(function () {
  const CSRF = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  async function request(method, url, body) {
    const opts = {
      method,
      headers: { "Accept": "application/json" },
      credentials: "same-origin",
    };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && CSRF) {
      opts.headers["X-CSRF-Token"] = CSRF;
    }
    const res = await fetch(url, opts);
    let data = null;
    const ctype = res.headers.get("Content-Type") || "";
    if (ctype.includes("application/json")) {
      data = await res.json().catch(() => null);
    }
    if (!res.ok) {
      const msg = (data && data.error) || `Request failed (${res.status}).`;
      const err = new Error(msg);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  window.API = {
    get: (url) => request("GET", url),
    post: (url, body) => request("POST", url, body),
    put: (url, body) => request("PUT", url, body),
    del: (url, body) => request("DELETE", url, body),
  };
})();
