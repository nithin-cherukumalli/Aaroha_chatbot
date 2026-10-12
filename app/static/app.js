(() => {
  const state = { identity: null, csrf: null, sourceOpener: null };
  const $ = (selector) => document.querySelector(selector);
  const api = async (path, options = {}) => {
    const headers = { ...(options.headers || {}) };
    if (state.csrf && !["GET", "HEAD"].includes(options.method || "GET")) headers["X-CSRF-Token"] = state.csrf;
    const response = await fetch(`/api/v1${path}`, { credentials: "same-origin", ...options, headers });
    if (response.status === 204) return null;
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error?.user_message || "The request could not be completed.");
    return payload.data;
  };
  const notice = (message) => { const el = $("#notice"); el.textContent = message; el.style.display = "block"; window.setTimeout(() => { el.style.display = "none"; }, 4400); };
  const escape = (value) => String(value).replace(/[&<>"']/g, (item) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" }[item]));
  const cookie = (name) => document.cookie.split("; ").find((item) => item.startsWith(`${name}=`))?.split("=")[1];
  const formatDate = (value) => value ? new Date(value).toLocaleDateString(undefined, { year:"numeric", month:"short", day:"numeric" }) : "—";

  function showView(view) {
    $("#chat-view").hidden = view !== "chat"; $("#knowledge-view").hidden = view !== "knowledge";
    document.querySelectorAll(".nav-link").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
    if (view === "knowledge") loadDocuments();
  }
  function openDialog(id, opener) { state.sourceOpener = opener || document.activeElement; $(id).showModal(); }
  function closeDialog(dialog) { dialog.close(); state.sourceOpener?.focus(); }
  function addMessage(type, content, result) {
    $("#empty-state").hidden = true;
    const shell = document.createElement("article"); shell.className = `message ${type}-message`;
    const label = type === "user" ? "You" : ({ approved_answer:"Approved answer", answer_from_documents:"Answer from documents", source_excerpts:"Source excerpts", insufficient_evidence:"Insufficient evidence" }[result?.mode] || "Assistant");
    shell.innerHTML = `<span class="message-label">${label}</span><div class="${type === "user" ? "user-message" : "assistant-message"}">${escape(content)}</div>`;
    if (result?.citations?.length) {
      const citations = document.createElement("div"); citations.className = "citations";
      result.citations.forEach((citation) => { const button = document.createElement("button"); button.className = "citation"; button.type = "button"; button.textContent = `${citation.label} · ${citation.filename}`; button.addEventListener("click", () => openSource(citation, button)); citations.append(button); });
      shell.append(citations);
    }
    $("#messages").append(shell);
  }
  function openSource(source, opener) {
    $("#source-title").textContent = source.filename; $("#source-meta").innerHTML = `<dt>Reference</dt><dd>${escape(source.label)}</dd><dt>Location</dt><dd>${escape(source.page ? `Page ${source.page}` : source.section || "Document section")}</dd>`; $("#source-excerpt").textContent = source.excerpt; openDialog("#source-dialog", opener);
  }
  async function sendQuestion(question) {
    const button = $("#send"); button.disabled = true; $("#question").disabled = true; addMessage("user", question);
    try { const result = await api("/chat", { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify({ question }) }); addMessage("assistant", result.answer, result); }
    catch (error) { addMessage("assistant", `Unable to answer: ${error.message}`); }
    finally { button.disabled = false; $("#question").disabled = false; $("#question").focus(); }
  }
  async function loadDocuments() {
    const tbody = $("#documents-body"); tbody.innerHTML = "";
    try {
      const result = await api("/documents"); $("#documents-empty").hidden = result.length > 0;
      result.forEach((doc) => {
        const actions = []; if (doc.status === "AWAITING_APPROVAL") actions.push(`<button class="secondary" data-action="approve" data-id="${doc.id}">Approve</button>`); if (["FAILED", "OCR_REQUIRED"].includes(doc.status)) actions.push(`<button class="secondary" data-action="retry" data-id="${doc.id}">Retry</button>`); if (doc.status === "READY") actions.push(`<button class="secondary" data-action="deactivate" data-id="${doc.id}">Deactivate</button>`); if (doc.status === "INACTIVE") actions.push(`<button class="secondary" data-action="reactivate" data-id="${doc.id}">Reactivate</button>`); if (doc.status !== "DELETED") actions.push(`<button class="secondary" data-action="delete" data-id="${doc.id}">Delete</button>`);
        const row = document.createElement("tr"); row.innerHTML = `<td data-label="Filename">${escape(doc.filename)}</td><td data-label="Type">${escape(doc.type.toUpperCase())}</td><td data-label="Status"><span class="status ${doc.status.toLowerCase()}">${escape(doc.status.replaceAll("_", " "))}</span></td><td data-label="Added">${formatDate(doc.added_at)}</td><td data-label="Actions"><div class="row-actions">${actions.join("")}</div></td>`; tbody.append(row);
      });
    } catch (error) { notice(error.message); }
  }
  async function loadQuestions() {
    const list = $("#questions-list"); list.innerHTML = "";
    try { const rows = await api("/pending-questions"); list.innerHTML = rows.length ? "" : '<p class="quiet">No pending questions.</p>'; rows.forEach((row) => { const node = document.createElement("div"); node.className = "question-item"; node.innerHTML = `<div><p>${escape(row.question)}</p><small>${escape(row.state)} · ${formatDate(row.created_at)}</small></div>${row.state === "open" ? `<button class="secondary" data-question-id="${row.id}">Resolve</button>` : ""}`; list.append(node); }); } catch (error) { notice(error.message); }
  }
  async function updateIdentity() {
    try { state.identity = await api("/identity"); $("#account-button").textContent = state.identity.email || "Account"; const curator = state.identity.role === "curator"; document.querySelectorAll(".curator-only").forEach((el) => el.hidden = !curator); }
    catch { state.identity = null; $("#account-button").textContent = "Sign in"; }
  }
  $("#composer").addEventListener("submit", (event) => { event.preventDefault(); const value = $("#question").value.trim(); if (!value) return; $("#question").value = ""; sendQuestion(value); });
  $("#question").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("#composer").requestSubmit(); } });
  document.querySelectorAll(".example").forEach((button) => button.addEventListener("click", () => { $("#question").value = button.textContent; $("#question").focus(); }));
  document.querySelectorAll(".nav-link").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  $("#account-button").addEventListener("click", () => state.identity ? notice(`Signed in as ${state.identity.email || "a member"}.`) : openDialog("#auth-dialog"));
  $("#open-upload").addEventListener("click", () => openDialog("#upload-dialog"));
  document.querySelectorAll(".close-dialog").forEach((button) => button.addEventListener("click", () => closeDialog(button.closest("dialog"))));
  $("#auth-form").addEventListener("submit", async (event) => { event.preventDefault(); try { const response = await fetch("/api/v1/auth/session", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ access_token: $("#access-token").value.trim() }) }); if (!response.ok) throw new Error("Sign-in token could not be verified."); state.csrf = response.headers.get("X-CSRF-Token") || decodeURIComponent(cookie("ae_csrf") || ""); closeDialog($("#auth-dialog")); await updateIdentity(); notice("Signed in."); } catch (error) { notice(error.message); } });
  $("#upload-form").addEventListener("submit", async (event) => { event.preventDefault(); const files = [...$("#files").files]; const progress = $("#upload-progress"); progress.innerHTML = ""; for (const file of files) { const line = document.createElement("div"); line.textContent = `${file.name}: uploading…`; progress.append(line); const form = new FormData(); form.append("file", file); form.append("content_mode", $("#content-mode").value); try { await api("/documents", { method:"POST", body:form }); line.textContent = `${file.name}: queued for extraction`; } catch (error) { line.textContent = `${file.name}: ${error.message}`; } } loadDocuments(); });
  $("#documents-body").addEventListener("click", async (event) => { const button = event.target.closest("button[data-action]"); if (!button) return; const { action, id } = button.dataset; if (action === "delete" && !window.confirm("Make this document unavailable and schedule permanent deletion?")) return; try { await api(action === "approve" ? `/documents/${id}/approve` : action === "retry" ? `/documents/${id}/retry` : `/documents/${id}`, { method: action === "approve" || action === "retry" ? "POST" : "PATCH", headers:{"Content-Type":"application/json"}, body: action === "approve" || action === "retry" ? undefined : JSON.stringify({ action }) }); loadDocuments(); notice(`Document ${action} requested.`); } catch (error) { notice(error.message); } });
  $("#documents-tab").addEventListener("click", () => { $("#documents-panel").hidden = false; $("#questions-panel").hidden = true; $("#documents-tab").setAttribute("aria-selected", "true"); $("#questions-tab").setAttribute("aria-selected", "false"); });
  $("#questions-tab").addEventListener("click", () => { $("#documents-panel").hidden = true; $("#questions-panel").hidden = false; $("#documents-tab").setAttribute("aria-selected", "false"); $("#questions-tab").setAttribute("aria-selected", "true"); loadQuestions(); });
  $("#questions-list").addEventListener("click", async (event) => { const button = event.target.closest("button[data-question-id]"); if (!button) return; try { await api(`/pending-questions/${button.dataset.questionId}`, { method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ state:"resolved" }) }); loadQuestions(); } catch (error) { notice(error.message); } });
  state.csrf = decodeURIComponent(cookie("ae_csrf") || ""); updateIdentity();
})();
