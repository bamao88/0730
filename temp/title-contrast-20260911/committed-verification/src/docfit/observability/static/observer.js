"use strict";

const statusNode = document.getElementById("action-status");
const csrfNode = document.querySelector('meta[name="docfit-csrf"]');
const csrfToken = csrfNode ? csrfNode.getAttribute("content") : null;

function announce(message, isError = false) {
  if (!statusNode) return;
  statusNode.textContent = message;
  statusNode.classList.toggle("is-error", isError);
  statusNode.classList.add("is-visible");
  window.setTimeout(() => statusNode.classList.remove("is-visible"), 5000);
}

async function readJson(response) {
  try { return await response.json(); }
  catch (_error) { return {status: "error", failure: {code: "observer_response_invalid"}}; }
}

async function copyText(value) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch (_error) { /* use the local DOM fallback below */ }
  }
  const field = document.createElement("textarea");
  field.value = value;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.appendChild(field);
  field.select();
  const copied = document.execCommand("copy");
  field.remove();
  return copied;
}

document.querySelectorAll("[data-post-url]").forEach((node) => {
  node.addEventListener("click", async () => {
    if (!(node instanceof HTMLElement) || !csrfToken) return;
    const question = node.dataset.confirm;
    if (question && !window.confirm(question)) return;
    node.setAttribute("aria-busy", "true");
    const response = await fetch(node.dataset.postUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {"x-docfit-csrf": csrfToken}
    });
    const payload = await readJson(response);
    node.removeAttribute("aria-busy");
    if (!response.ok) {
      if (response.status === 401) {
        window.location.assign("/");
        return;
      }
      announce(payload.failure?.code || payload.failure_code || "observer_action_failed", true);
      return;
    }
    announce(payload.status || "ok");
    const redirect = node.dataset.redirect;
    if (redirect) window.location.assign(redirect);
    else if (node.dataset.postUrl?.includes("/mount") || node.dataset.postUrl?.includes("/delete")) window.location.reload();
  });
});

document.querySelectorAll("[data-copy-json]").forEach((node) => {
  node.addEventListener("click", async () => {
    if (!(node instanceof HTMLElement)) return;
    const response = await fetch(node.dataset.copyJson, {credentials: "same-origin"});
    const payload = await readJson(response);
    if (!response.ok) {
      if (response.status === 401) {
        window.location.assign("/");
        return;
      }
      announce(payload.failure?.code || "observer_copy_failed", true);
      return;
    }
    try {
      const copied = await copyText(JSON.stringify(payload, null, 2));
      announce(copied ? "调试上下文已复制" : "observer_clipboard_unavailable", !copied);
    } catch (_error) { announce("observer_clipboard_unavailable", true); }
  });
});

document.querySelectorAll("[data-copy-value]").forEach((node) => {
  node.addEventListener("click", async () => {
    if (!(node instanceof HTMLElement)) return;
    try {
      const copied = await copyText(node.dataset.copyValue || "");
      announce(copied ? "引用已复制" : "observer_clipboard_unavailable", !copied);
    } catch (_error) { announce("observer_clipboard_unavailable", true); }
  });
});

function startFallbackPolling() {
  let known = document.documentElement.dataset.revision || "";
  window.setInterval(async () => {
    try {
      const response = await fetch("/api/revision", {credentials: "same-origin", cache: "no-store"});
      if (response.status === 401) {
        window.location.assign("/");
        return;
      }
      if (!response.ok) return;
      const payload = await response.json();
      if (known && payload.revision !== known) window.location.reload();
      known = payload.revision;
    } catch (_error) { /* bounded retry on the next interval */ }
  }, 5000);
}

if (csrfToken && "EventSource" in window) {
  const stream = new EventSource("/api/stream");
  stream.addEventListener("history", (event) => {
    const payload = JSON.parse(event.data);
    const known = document.documentElement.dataset.revision || "";
    if (known && payload.revision !== known) window.location.reload();
  });
  stream.onerror = () => { stream.close(); startFallbackPolling(); };
} else if (csrfToken) startFallbackPolling();
