const SERVER = "http://127.0.0.1:8765";
const pairingInput = document.querySelector("#pairing-code");
const status = document.querySelector("#status");
const saveButton = document.querySelector("#save-button");
const shareButton = document.querySelector("#share-button");
const refreshActionsButton = document.querySelector("#refresh-actions-button");
const runActionButton = document.querySelector("#run-action-button");
let approvedAction = null;
let reviewedForm = null;

function showStatus(message, kind = "") {
  status.textContent = message;
  status.className = kind;
}

async function storedToken() {
  const value = await chrome.storage.local.get("shepardPairingCode");
  return String(value.shepardPairingCode || "").trim();
}

async function bridgeRequest(path, payload = null, token = null) {
  const pairingCode = token || await storedToken();
  if (!pairingCode) throw new Error("Add the pairing code from Shepard first");
  const response = await fetch(SERVER + path, {
    method: payload === null ? "GET" : "POST",
    headers: { "Content-Type": "application/json", "X-Shepard-Bridge": pairingCode },
    body: payload === null ? undefined : JSON.stringify(payload)
  });
  const value = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(value.error || `Shepard returned ${response.status}`);
  return value;
}

function normalUrl(value) {
  const url = new URL(value);
  url.hash = "";
  return url.href;
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !/^https?:\/\//.test(tab.url || "")) {
    throw new Error("Open a normal http:// or https:// webpage first");
  }
  return tab;
}

function renderApprovedAction(action) {
  approvedAction = action || null;
  reviewedForm = null;
  document.querySelector("#no-actions").hidden = Boolean(action);
  document.querySelector("#action-card").hidden = !action;
  document.querySelector("#submit-review").hidden = true;
  document.querySelector("#confirm-submit").checked = false;
  if (!action) return;
  document.querySelector("#action-title").textContent = action.action === "navigate"
    ? "Navigate active tab" : "Submit current form";
  document.querySelector("#action-description").textContent = action.description;
  document.querySelector("#action-url").textContent = action.url;
  runActionButton.textContent = action.action === "submit" ? "Review approved form" : "Run approved navigation";
}

async function loadApprovedActions() {
  refreshActionsButton.disabled = true;
  try {
    const result = await bridgeRequest("/api/browser/actions");
    renderApprovedAction(result.actions?.[0] || null);
  } finally {
    refreshActionsButton.disabled = false;
  }
}

function inspectSafeForm(expectedUrl) {
  const normal = (value) => { const url = new URL(value); url.hash = ""; return url.href; };
  if (normal(location.href) !== normal(expectedUrl)) {
    return { error: "The active page does not match the approved page." };
  }
  const forbidden = /(password|passcode|card|credit|cvv|cvc|routing|bank|account.?number|social.?security|ssn)/i;
  const forms = [...document.forms].filter((form) => {
    const style = getComputedStyle(form);
    const rect = form.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0
      && String(form.method || "get").toLowerCase() !== "get";
  });
  const safe = forms.filter((form) => ![...form.elements].some((field) =>
    field.type === "password" || forbidden.test(`${field.name || ""} ${field.id || ""} ${field.autocomplete || ""}`)
  ));
  if (forms.length !== safe.length) return { error: "This form contains password, payment, banking, or identity fields and cannot be submitted by Wayfinder." };
  if (safe.length !== 1) return { error: `Wayfinder requires exactly one visible non-search form; this page has ${safe.length}.` };
  const form = safe[0];
  const destination = new URL(form.action || location.href, location.href);
  if (location.protocol === "https:" && destination.protocol !== "https:") {
    return { error: "The form would downgrade from HTTPS and was blocked." };
  }
  const fields = [...form.elements]
    .filter((field) => field.name && !["hidden", "submit", "button"].includes(field.type))
    .map((field) => field.name).slice(0, 12);
  return {
    formIndex: [...document.forms].indexOf(form),
    destination: destination.href,
    method: String(form.method || "post").toUpperCase(),
    fields,
  };
}

function submitSafeForm(expectedUrl, formIndex) {
  const normal = (value) => { const url = new URL(value); url.hash = ""; return url.href; };
  if (normal(location.href) !== normal(expectedUrl)) return { error: "The active page changed after review." };
  const form = document.forms[formIndex];
  if (!form) return { error: "The reviewed form is no longer on the page." };
  const forbidden = /(password|passcode|card|credit|cvv|cvc|routing|bank|account.?number|social.?security|ssn)/i;
  if ([...form.elements].some((field) => field.type === "password" || forbidden.test(`${field.name || ""} ${field.id || ""} ${field.autocomplete || ""}`))) {
    return { error: "Sensitive fields appeared after review; submission was blocked." };
  }
  if (!form.checkValidity()) return { error: "The form has missing or invalid fields. Complete them before submitting." };
  form.requestSubmit();
  return { submitted: true };
}

async function finishAction(outcome, detail) {
  await bridgeRequest(`/api/browser/actions/${encodeURIComponent(approvedAction.id)}/complete`, {
    outcome, detail
  });
  showStatus(detail, outcome === "executed" ? "good" : "error");
  await loadApprovedActions();
}

async function runApprovedAction() {
  if (!approvedAction) throw new Error("No approved browser action is waiting");
  runActionButton.disabled = true;
  try {
    const tab = await activeTab();
    if (approvedAction.action === "navigate") {
      await chrome.tabs.update(tab.id, { url: approvedAction.url });
      await finishAction("executed", `Wayfinder opened ${approvedAction.url}`);
      return;
    }
    if (normalUrl(tab.url) !== normalUrl(approvedAction.url)) {
      throw new Error("Open the exact approved page before reviewing its form");
    }
    if (!reviewedForm) {
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id }, func: inspectSafeForm, args: [approvedAction.url]
      });
      const review = results?.[0]?.result;
      if (!review || review.error) throw new Error(review?.error || "The form could not be reviewed");
      reviewedForm = review;
      document.querySelector("#submit-review").hidden = false;
      document.querySelector("#submit-review-copy").textContent =
        `${review.method} to ${review.destination}. Fields: ${review.fields.join(", ") || "unnamed fields"}. No field values were read.`;
      runActionButton.textContent = "Submit reviewed form";
      showStatus("Review the destination, check the confirmation box, then submit", "");
      return;
    }
    if (!document.querySelector("#confirm-submit").checked) {
      throw new Error("Check the final confirmation box first");
    }
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: submitSafeForm,
      args: [approvedAction.url, reviewedForm.formIndex]
    });
    const result = results?.[0]?.result;
    if (!result || result.error) throw new Error(result?.error || "The form was not submitted");
    await finishAction("executed", `Wayfinder submitted the reviewed form on ${approvedAction.url}`);
  } finally {
    runActionButton.disabled = false;
  }
}

async function saveAndTest() {
  const token = pairingInput.value.trim();
  if (!token) throw new Error("Paste the pairing code shown in Shepard Connections");
  saveButton.disabled = true;
  try {
    await bridgeRequest("/api/browser/ping", {}, token);
    await chrome.storage.local.set({ shepardPairingCode: token });
    pairingInput.value = token;
    showStatus("Connected to local Shepard", "good");
  } finally {
    saveButton.disabled = false;
  }
}

function extractReadablePage() {
  const clone = document.body?.cloneNode(true);
  if (!clone) return { title: document.title, url: location.href, text: "" };
  clone.querySelectorAll("script, style, noscript, svg, canvas, iframe, template").forEach((node) => node.remove());
  return {
    title: document.title,
    url: location.href,
    text: String(clone.innerText || clone.textContent || "").replace(/\s+/g, " ").trim().slice(0, 50000)
  };
}

async function shareCurrentPage() {
  shareButton.disabled = true;
  try {
    const tab = await activeTab();
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractReadablePage
    });
    const page = results?.[0]?.result;
    if (!page?.text) throw new Error("This page has no readable text to share");
    const result = await bridgeRequest("/api/browser/pages", page);
    showStatus(`Shared “${result.title}” with Shepard`, "good");
  } finally {
    shareButton.disabled = false;
  }
}

saveButton.addEventListener("click", () => saveAndTest().catch((error) => showStatus(error.message, "error")));
shareButton.addEventListener("click", () => shareCurrentPage().catch((error) => showStatus(error.message, "error")));
refreshActionsButton.addEventListener("click", () => loadApprovedActions().catch((error) => showStatus(error.message, "error")));
runActionButton.addEventListener("click", () => runApprovedAction().catch((error) => showStatus(error.message, "error")));
document.querySelector("#open-button").addEventListener("click", () => chrome.tabs.create({ url: SERVER + "/" }));

storedToken().then(async (token) => {
  pairingInput.value = token;
  if (!token) return;
  try {
    await bridgeRequest("/api/browser/ping", {}, token);
    showStatus("Connected to local Shepard", "good");
    await loadApprovedActions();
  } catch {
    showStatus("Saved code could not reach Shepard", "error");
  }
});
