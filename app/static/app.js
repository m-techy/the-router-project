(() => {
  "use strict";

  const state = {
    providers: [],
    usage: [],
    health: null,
    setup: null,
    snippets: null,
    catalog: null,
    projects: null,
    routes: [],
    doctor: null,
    newProjectKey: null,
    activeSnippet: "python",
    currentView: "overview",
  };

  const VIEW_META = {
    overview: ["Overview", "Free capacity at a glance."],
    setup: ["Setup", "Connect providers and configure this router."],
    projects: ["Projects", "Local router keys and daily usage limits."],
    routes: ["Routes", "Named routing policy for each application."],
    doctor: ["Doctor", "Readiness, redundancy, and safety checks."],
    guide: ["Guide", "Run, configure, test, and integrate."],
    providers: ["Providers", "Quota, health, models, and live probes."],
    playground: ["Playground", "Test routing before changing your app."],
    usage: ["Usage & traces", "Inspect requests and fallback chains."],
    catalog: ["Catalog review", "Review upstream model changes safely."],
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (char) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[char],
    );
  const fmt = (value) => new Intl.NumberFormat().format(Number(value || 0));
  const pct = (value) =>
    Math.max(0, Math.min(100, Math.round(Number(value || 0) * 100)));

  function toast(message, tone = "neutral") {
    const host = $("#toastHost");
    if (!host) return;
    const node = document.createElement("div");
    node.className = `toast toast-${tone}`;
    node.textContent = message;
    host.appendChild(node);
    requestAnimationFrame(() => node.classList.add("show"));
    window.setTimeout(() => {
      node.classList.remove("show");
      window.setTimeout(() => node.remove(), 250);
    }, 2300);
  }

  async function copyText(text, successMessage = "Copied") {
    try {
      await navigator.clipboard.writeText(text);
      toast(successMessage, "good");
      return;
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
      toast(successMessage, "good");
    }
  }

  function adminKey() {
    return window.sessionStorage.getItem("routerAdminKey") || "";
  }

  function projectKey() {
    return window.sessionStorage.getItem("routerProjectKey") || "";
  }

  function inferenceHeaders(headers = {}) {
    const key = projectKey();
    return {
      ...headers,
      ...(key ? { Authorization: `Bearer ${key}` } : {}),
    };
  }

  function authHeaders(headers = {}) {
    const key = adminKey();
    return {
      ...headers,
      ...(key ? { Authorization: `Bearer ${key}` } : {}),
    };
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: authHeaders({
        "Content-Type": "application/json",
        ...(options.headers || {}),
      }),
    });

    const text = await response.text();
    let payload = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = text;
      }
    }

    if (!response.ok) {
      const detail =
        payload && typeof payload === "object"
          ? payload.detail || payload.message || JSON.stringify(payload)
          : payload || response.statusText;
      throw new Error(detail);
    }

    return payload;
  }

  function setView(view) {
    if (!VIEW_META[view]) return;
    state.currentView = view;
    $$(".view").forEach((node) => node.classList.toggle("active", node.id === view));
    $$(".nav").forEach((node) =>
      node.classList.toggle("active", node.dataset.view === view),
    );
    const [title, subtitle] = VIEW_META[view];
    $("#viewTitle").textContent = title;
    $("#viewSubtitle").textContent = subtitle;
    history.replaceState(null, "", `#${view}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function stat(label, value, detail = "") {
    return `
      <div class="telemetry-cell">
        <span>${esc(label)}</span>
        <strong>${esc(value)}</strong>
        <small>${esc(detail)}</small>
      </div>
    `;
  }

  function renderRequestTable(events, withTrace = true) {
    if (!events.length) {
      return '<div class="empty-state">No routed requests yet.</div>';
    }
    return `
      <table>
        <thead>
          <tr>
            <th>Provider</th>
            <th>Model</th>
            <th>Status</th>
            <th>Latency</th>
            ${withTrace ? "<th>Trace</th>" : ""}
          </tr>
        </thead>
        <tbody>
          ${events
            .map(
              (event) => `
              <tr>
                <td>${esc(event.provider_id)}</td>
                <td>${esc(event.model_id)}</td>
                <td class="${event.success ? "ok" : "err"}">
                  ${event.success ? "OK" : esc(event.status_code || "ERR")}
                </td>
                <td>${event.latency_ms ? `${Math.round(event.latency_ms)} ms` : "—"}</td>
                ${withTrace
                  ? `<td>${
                      event.request_id
                        ? `<button type="button" class="trace-link" data-request="${esc(event.request_id)}">${esc(event.request_id.slice(-8))}</button>`
                        : "—"
                    }</td>`
                  : ""}
              </tr>
            `,
            )
            .join("")}
        </tbody>
      </table>
    `;
  }

  function renderOverview() {
    const providers = state.providers;
    const configured = providers.filter((provider) => provider.configured);
    const persistent = configured.filter(
      (provider) => provider.tier === "persistent_free",
    );
    const healthy = configured.filter((provider) =>
      ["active", "unknown"].includes(provider.certification?.state || "unknown"),
    );
    const models = providers.reduce(
      (total, provider) => total + (provider.models?.length || 0),
      0,
    );

    $("#stats").innerHTML =
      stat("Connected pools", configured.length, `${persistent.length} recurring-free`) +
      stat("Reviewed models", models, "eligible catalog entries") +
      stat(
        "Requests / 24h",
        state.usage.length,
        `${state.usage.filter((event) => event.success).length} successful`,
      ) +
      stat("Healthy pools", healthy.length, "configured and available");

    const capacityProviders = (configured.length ? configured : providers).slice(0, 10);
    $("#capacityList").innerHTML =
      capacityProviders
        .map((provider) => {
          const headroom = provider.runtime?.headroom ?? 0.65;
          return `
            <div class="capacity-row">
              <div>
                <strong>${esc(provider.name)}</strong>
                <span>${esc(provider.tier)}</span>
              </div>
              <div class="meter"><i style="width:${pct(headroom)}%"></i></div>
              <b>${pct(headroom)}%</b>
            </div>
          `;
        })
        .join("") ||
      '<div class="empty-state">Connect a provider to see capacity.</div>';

    $("#recentMini").innerHTML = renderRequestTable(state.usage.slice(0, 7), false);
  }

  function setupRequirementRow(requirement, writable) {
    const source = requirement.source || "missing";
    const configured = Boolean(requirement.configured);
    const status = configured
      ? `<span class="status-word ready">${esc(source)}</span>`
      : '<span class="status-word missing">missing</span>';

    let control = "";
    if (writable && source !== "environment") {
      if (configured) {
        control = `
          <button type="button" class="row-action setup-remove" data-key="${esc(requirement.key)}">
            remove
          </button>
        `;
      } else {
        control = `
          <div class="setup-input">
            <input
              type="${requirement.secret ? "password" : "text"}"
              autocomplete="off"
              placeholder="${esc(requirement.label)}"
              data-setup-input="${esc(requirement.key)}"
            />
            <button type="button" class="row-action setup-save" data-key="${esc(requirement.key)}">
              save
            </button>
          </div>
        `;
      }
    }

    return `
      <div class="credential-line">
        <div class="credential-key">
          <strong>${esc(requirement.label)}${requirement.optional ? " · optional" : ""}</strong>
          <span>${esc(requirement.key)}</span>
        </div>
        <div class="credential-control">${status}${control}</div>
      </div>
    `;
  }

  function renderSetup() {
    const setup = state.setup || {};
    const total = Math.max(1, setup.providers_total || 1);
    const readiness = Math.round(((setup.providers_ready || 0) / total) * 100);

    $("#setupReadiness").innerHTML = `
      <div class="readiness-dial" style="--readiness:${readiness * 3.6}deg">
        <div><strong>${readiness}%</strong><span>ready</span></div>
      </div>
      <div class="readiness-copy">
        <strong>${setup.providers_ready || 0} / ${setup.providers_total || 0} providers</strong>
        <span>${setup.persistent_ready || 0} recurring-free · ${setup.no_key_ready || 0} no-key/optional-key</span>
        <div class="readiness-flags">
          <i>${esc(setup.transport || "direct")}</i>
          <i>promo ${setup.promo_enabled ? "on" : "off"}</i>
          <i>trial ${setup.trial_enabled ? "on" : "off"}</i>
          <i>vault ${setup.vault?.enabled ? "on" : "off"}</i>
          <i>projects ${setup.projects?.count || 0}</i>
          <i>state ${esc(setup.state?.backend || "sqlite")}</i>
          <i>${esc(setup.mode || "local-platform")}</i>
        </div>
      </div>
    `;

    const providers = setup.provider_setup || [];
    const rows = providers
      .filter((provider) => provider.requirements?.length || provider.no_key_required)
      .map((provider) => {
        const requirements = (provider.requirements || [])
          .map((requirement) =>
            setupRequirementRow(requirement, Boolean(setup.writable_setup)),
          )
          .join("");

        return `
          <article class="credential-provider">
            <div class="credential-provider-main">
              <span class="provider-index">${esc(provider.id)}</span>
              <div>
                <strong>${esc(provider.name)}</strong>
                <small>${esc(provider.tier)}${provider.no_key_required ? " · no key required" : ""}</small>
              </div>
              <span class="status-word ${provider.ready ? "ready" : "missing"}">
                ${provider.ready ? "ready" : "setup"}
              </span>
            </div>
            <div class="credential-requirements">
              ${requirements || '<div class="credential-line"><span class="muted-line">No credentials required.</span></div>'}
            </div>
            <div class="provider-links">
              ${provider.signup_url ? `<a href="${esc(provider.signup_url)}" target="_blank" rel="noreferrer">Get key ↗</a>` : ""}
              ${provider.docs_url ? `<a href="${esc(provider.docs_url)}" target="_blank" rel="noreferrer">Docs ↗</a>` : ""}
            </div>
          </article>
        `;
      });

    $("#setupMissing").innerHTML =
      rows.join("") ||
      '<div class="empty-state">No provider configuration is required.</div>';

    if (!setup.writable_setup) {
      $("#setupMissing").insertAdjacentHTML(
        "afterbegin",
        '<div class="inline-warning">Credential writes are disabled in hosted mode. Use deployment environment variables.</div>',
      );
    }

    const vault = setup.vault || {};
    const projectState = setup.projects || {};
    const vaultSummary = $("#vaultSummary");
    if (vaultSummary) {
      vaultSummary.textContent = vault.enabled
        ? `Vault on · ${vault.encrypted_secrets || 0}/${vault.stored_secrets || 0} stored secrets encrypted`
        : `Vault off · ${vault.stored_secrets || 0} local secrets stored without vault encryption`;
    }
    if (projectState.enforced) {
      $("#projectEnforcement")?.replaceChildren(
        document.createTextNode("Project keys enforced")
      );
    }

    renderSnippet();
  }

  function renderSnippet() {
    let code =
      state.snippets?.snippets?.[state.activeSnippet] ||
      "Start the local router to generate a client snippet.";
    const key = projectKey();
    if (key) {
      code = code
        .replace('api_key="local"', `api_key="${key}"`)
        .replace('apiKey: "local"', `apiKey: "${key}"`);
      if (
        state.activeSnippet === "curl"
        && !code.includes("Authorization: Bearer")
      ) {
        code = code.replace(
          '-H "Content-Type: application/json"',
          `-H "Content-Type: application/json" \\\n  -H "Authorization: Bearer ${key}"`,
        );
      }
    }
    $("#snippetCode").textContent = code;
    $$(".snippet-tab").forEach((button) =>
      button.classList.toggle(
        "active",
        button.dataset.snippet === state.activeSnippet,
      ),
    );
  }

  function modelKind(model) {
    const caps = model.capabilities || {};
    if (caps.transcription) return "asr";
    if (caps.embeddings) return caps.vision || caps.audio ? "embed+" : "embed";
    if (caps.image_generation) return "image";
    if (caps.vision) return "vision";
    return "chat";
  }

  function renderProviders() {
    const query = ($("#providerSearch")?.value || "").toLowerCase();
    const tier = $("#tierFilter")?.value || "all";

    const providers = state.providers.filter((provider) => {
      const searchable = `${provider.name} ${provider.id} ${(provider.models || [])
        .map((model) => model.id)
        .join(" ")}`.toLowerCase();
      return (tier === "all" || provider.tier === tier) && searchable.includes(query);
    });

    $("#providerGrid").innerHTML =
      providers
        .map((provider, index) => {
          const certification = provider.certification?.state || "unknown";
          const telemetry = provider.runtime?.provider_quota || {};
          const headroom = pct(provider.runtime?.headroom ?? 0);
          const models = (provider.models || []).slice(0, 4);

          return `
            <article class="provider-row">
              <div class="provider-row-index">${String(index + 1).padStart(2, "0")}</div>
              <div class="provider-row-name">
                <div class="provider-name-line">
                  <span class="connection-dot ${provider.configured ? "connected" : ""}"></span>
                  <strong>${esc(provider.name)}</strong>
                </div>
                <small>${esc(provider.id)} · ${esc(provider.tier)}</small>
              </div>
              <div class="provider-row-models">
                ${models.map((model) => `<span>${esc(model.label || model.id)} <i>${esc(modelKind(model))}</i></span>`).join("")}
                ${provider.models?.length > 4 ? `<small>+${provider.models.length - 4}</small>` : ""}
              </div>
              <div class="provider-row-health">
                <span>${esc(certification)}</span>
                <div class="headroom-track"><i style="width:${headroom}%"></i></div>
                <small>${headroom}% headroom</small>
              </div>
              <div class="provider-row-meta">
                ${telemetry.credit_limit_remaining !== undefined ? `<span>credit ${esc(telemetry.credit_limit_remaining)}</span>` : ""}
                ${telemetry.credit_usage_daily !== undefined ? `<span>daily ${esc(telemetry.credit_usage_daily)}</span>` : ""}
                ${provider.docs_url ? `<a href="${esc(provider.docs_url)}" target="_blank" rel="noreferrer">docs ↗</a>` : ""}
              </div>
              <div class="provider-row-actions">
                ${provider.id === "openrouter" ? `<button type="button" class="row-action quota-refresh" data-provider="${esc(provider.id)}">quota</button>` : ""}
                <button type="button" class="row-action certify" data-provider="${esc(provider.id)}">probe</button>
              </div>
            </article>
          `;
        })
        .join("") || '<div class="empty-state">No providers match this filter.</div>';
  }

  function renderCatalog() {
    const report = state.catalog || {};

    if (!report.available) {
      $("#catalogStats").innerHTML =
        stat("Report", "Not generated", "run discovery + reconciliation") +
        stat("Auto promotion", "Off", "review required") +
        stat("Source", "free-coding-models", "safe text parse") +
        stat("Routing impact", "None", "until registry edit");
      $("#catalogStatus").textContent =
        report.message || "No reconciliation report yet.";
      $("#catalogChanges").innerHTML =
        '<div class="setup-note">Run python scripts/fcm_discovery.py and python scripts/reconcile_fcm.py on the router host to populate this queue.</div>';
      return;
    }

    const providers = report.providers || {};
    const changed = Object.entries(providers).filter(
      ([, value]) =>
        (value.candidate_additions?.length || 0) +
          (value.missing_upstream?.length || 0) >
        0,
    );

    $("#catalogStats").innerHTML =
      stat("New candidates", fmt(report.candidate_additions), "not routable yet") +
      stat("Missing upstream", fmt(report.missing_upstream), "review for retirement") +
      stat("Providers changed", changed.length, "need human review") +
      stat("Auto promotion", "Off", "safe by design");

    $("#catalogStatus").textContent =
      "Review-only diff. Nothing enters free/auto until the registry is explicitly updated.";

    $("#catalogChanges").innerHTML = changed.length
      ? changed
          .map(([id, value]) => {
            const additions = (value.candidate_additions || [])
              .map((model) => `<span class="catalog-chip add">+ ${esc(model)}</span>`)
              .join("");
            const removals = (value.missing_upstream || [])
              .map((model) => `<span class="catalog-chip remove">− ${esc(model)}</span>`)
              .join("");
            return `
              <div class="catalog-provider">
                <div class="catalog-provider-head">
                  <strong>${esc(id)}</strong>
                  <span>${fmt(value.reviewed_count)} reviewed / ${fmt(value.upstream_count)} upstream</span>
                </div>
                <div class="catalog-chips">${additions}${removals}</div>
              </div>
            `;
          })
          .join("")
      : '<div class="success-box">Reviewed registry and upstream snapshot are aligned.</div>';
  }

  function renderProjects() {
    const host = $("#projectList");
    if (!host) return;

    if (!state.projects) {
      host.innerHTML =
        '<div class="empty-state">Project management is unavailable. If ROUTER_ADMIN_KEY is set, use the admin API directly.</div>';
      return;
    }

    $("#projectEnforcement").textContent = state.projects.enforced
      ? "Project keys enforced"
      : "Legacy local access enabled";

    const projects = state.projects.projects || [];
    host.innerHTML = projects.length
      ? projects
          .map((project) => {
            const usage = project.usage_today || {};
            const requestLimit = project.daily_request_limit;
            const tokenLimit = project.daily_token_limit;
            const requestText = requestLimit
              ? `${fmt(usage.requests)}/${fmt(requestLimit)} requests`
              : `${fmt(usage.requests)} requests · unlimited`;
            const tokenText = tokenLimit
              ? `${fmt(usage.tokens)}/${fmt(tokenLimit)} tokens`
              : `${fmt(usage.tokens)} tokens · unlimited`;
            return `
              <article class="project-row">
                <div class="project-identity">
                  <strong>${esc(project.name)}</strong>
                  <span>${esc(project.id)} · ${esc(project.key_prefix)}…</span>
                </div>
                <div class="project-usage">
                  <span>${esc(requestText)}</span>
                  <span>${esc(tokenText)}</span>
                </div>
                <div class="project-state">
                  <span class="status-word ${project.enabled ? "ready" : "missing"}">
                    ${project.enabled ? "active" : "disabled"}
                  </span>
                </div>
                <button type="button" class="row-action project-delete" data-project="${esc(project.id)}" data-prefix="${esc(project.key_prefix)}">
                  revoke
                </button>
              </article>
            `;
          })
          .join("")
      : '<div class="empty-state">No project keys yet. Create one above for an app that should have its own limit.</div>';
  }

  function renderRoutes() {
    const host = $("#routeList");
    if (!host) return;
    const routes = state.routes || [];

    host.innerHTML = routes.length
      ? routes
          .map((route) => {
            const allow = route.providers_allow?.length
              ? route.providers_allow.join(", ")
              : "any reviewed provider";
            const deny = route.providers_deny?.length
              ? route.providers_deny.join(", ")
              : "none";
            return `
              <article class="route-profile-row">
                <div class="route-profile-id">
                  <strong>${esc(route.model)}</strong>
                  <span>${esc(route.name)}</span>
                </div>
                <div class="route-profile-policy">
                  <span>strategy <b>${esc(route.base_route)}</b></span>
                  <span>fallbacks <b>${esc(route.max_fallbacks)}</b></span>
                  <span>context <b>${route.min_context ? fmt(route.min_context) : "any"}</b></span>
                </div>
                <div class="route-profile-scope">
                  <span>allow: ${esc(allow)}</span>
                  <span>deny: ${esc(deny)}</span>
                </div>
                <div class="route-profile-actions">
                  <button type="button" class="row-action route-copy" data-model="${esc(route.model)}">copy</button>
                  <button type="button" class="row-action route-delete" data-route="${esc(route.slug)}">delete</button>
                </div>
              </article>
            `;
          })
          .join("")
      : '<div class="empty-state">No custom routes yet. free/* remains the default policy surface.</div>';
  }

  function renderDoctor() {
    const report = state.doctor || {};
    const checks = report.checks || [];
    const score = $("#doctorScore");
    const summary = $("#doctorSummary");
    if (score) score.textContent = checks.length ? `${report.score || 0}/${report.checks_total || checks.length}` : "—";
    if (summary) {
      summary.textContent = report.warnings
        ? `${report.warnings} warning${report.warnings === 1 ? "" : "s"} need attention`
        : checks.length
          ? "No blocking readiness warnings"
          : "Doctor unavailable";
    }

    const host = $("#doctorChecks");
    if (!host) return;
    host.innerHTML = checks.length
      ? checks
          .map(
            (check) => `
              <article class="doctor-check doctor-${esc(check.status)}">
                <div class="doctor-check-head">
                  <span>${esc(check.status)}</span>
                  <strong>${esc(check.title)}</strong>
                </div>
                <p>${esc(check.detail)}</p>
                ${
                  check.action_view
                    ? `<button type="button" class="text-button doctor-action" data-view-jump="${esc(check.action_view)}">Open ${esc(check.action_view)} →</button>`
                    : ""
                }
              </article>
            `,
          )
          .join("")
      : '<div class="empty-state">No doctor report available.</div>';
  }

  function renderRouteModels() {
    const select = $("#playModel");
    if (!select) return;
    select.querySelectorAll("option[data-custom-route]").forEach((option) => option.remove());
    for (const route of state.routes || []) {
      const option = document.createElement("option");
      option.value = route.model;
      option.textContent = route.model;
      option.dataset.customRoute = "true";
      select.appendChild(option);
    }
  }

  function renderUsage(summary) {
    const totals = summary.totals || {};
    $("#usageStats").innerHTML =
      stat("Requests", fmt(totals.requests), "last 24 hours") +
      stat(
        "Successes",
        fmt(totals.successes),
        totals.requests
          ? `${Math.round((totals.successes / totals.requests) * 100)}% success`
          : "—",
      ) +
      stat("Tokens", fmt(totals.tokens), "reported by providers") +
      stat(
        "Avg latency",
        totals.avg_latency_ms ? `${Math.round(totals.avg_latency_ms)} ms` : "—",
        "successful + failed",
      );
    $("#usageTable").innerHTML = renderRequestTable(state.usage, true);
  }

  function playgroundRequest() {
    const messages = [];
    const system = $("#systemPrompt").value.trim();
    if (system) messages.push({ role: "system", content: system });
    messages.push({ role: "user", content: $("#userPrompt").value });
    return {
      model: $("#playModel").value,
      messages,
      stream: false,
      temperature: Number($("#temperature").value),
      max_tokens: Number($("#maxTokens").value),
    };
  }

  async function refreshQuota(providerId, button) {
    const original = button.textContent;
    button.textContent = "Refreshing…";
    button.disabled = true;
    try {
      await api(`/api/providers/${encodeURIComponent(providerId)}/quota/refresh`, {
        method: "POST",
      });
      toast("Quota telemetry updated", "good");
      await refresh();
    } catch (error) {
      toast(error.message || "Quota refresh unavailable", "bad");
    } finally {
      button.textContent = original;
      button.disabled = false;
    }
  }

  async function certify(providerId, button) {
    const original = button.textContent;
    button.textContent = "Probing…";
    button.disabled = true;
    try {
      const result = await api(
        `/api/providers/${encodeURIComponent(providerId)}/certify`,
        { method: "POST" },
      );
      toast(
        result.ok ? `${providerId} is active` : `${providerId}: ${result.state}`,
        result.ok ? "good" : "neutral",
      );
      await refresh();
    } catch (error) {
      toast(error.message || "Probe failed", "bad");
    } finally {
      button.textContent = original;
      button.disabled = false;
    }
  }

  async function loadTrace(requestId) {
    $("#traceId").textContent = requestId;
    $("#traceDetail").innerHTML = '<div class="sub">Loading trace…</div>';
    try {
      const result = await api(
        `/api/usage/trace/${encodeURIComponent(requestId)}`,
      );
      $("#traceDetail").innerHTML = result.events
        .map(
          (event, index) => `
            <div class="trace-step ${event.success ? "trace-ok" : "trace-fail"}">
              <div class="trace-index">${index + 1}</div>
              <div>
                <strong>${esc(event.provider_id)} / ${esc(event.model_id)}</strong>
                <div class="sub">
                  ${event.success ? "success" : `failed · ${esc(event.status_code || "error")}`}
                  · ${event.latency_ms ? `${Math.round(event.latency_ms)} ms` : "no latency"}
                  · ${fmt(event.total_tokens)} tokens
                </div>
                ${event.error ? `<div class="trace-error">${esc(event.error)}</div>` : ""}
              </div>
            </div>
          `,
        )
        .join("");
    } catch (error) {
      $("#traceDetail").innerHTML = `<div class="err">${esc(error.message)}</div>`;
    }
  }

  async function refresh() {
    $("#refreshBtn").classList.add("is-loading");
    try {
      const results = await Promise.allSettled([
        api("/health"),
        api("/api/providers"),
        api("/api/usage/recent?limit=100"),
        api("/api/usage/summary?hours=24"),
        api("/api/setup/status"),
        api("/api/setup/snippets"),
        api("/api/catalog/reconciliation"),
        api("/api/projects"),
        api("/api/routes"),
        api("/api/doctor"),
      ]);

      const [health, providers, usage, summary, setup, snippets, catalog, projects, routes, doctor] =
        results.map((result) =>
          result.status === "fulfilled" ? result.value : null,
        );

      if (!health || !providers) {
        throw new Error("Router core endpoints are unavailable");
      }

      state.health = health;
      state.providers = providers.providers || [];
      state.usage = usage?.events || [];
      state.setup = setup || {};
      state.snippets = snippets || {};
      state.catalog = catalog || { available: false };
      state.projects = projects;
      state.routes = routes?.routes || [];
      state.doctor = doctor;

      $("#healthDot").classList.add("online");
      $("#healthLabel").textContent =
        `${health.configured_providers}/${health.providers} providers configured`;

      renderOverview();
      renderSetup();
      renderProviders();
      renderUsage(summary || { totals: {} });
      renderCatalog();
      renderProjects();
      renderRoutes();
      renderDoctor();
      renderRouteModels();
    } catch (error) {
      $("#healthDot").classList.remove("online");
      $("#healthLabel").textContent = "Router unavailable";
      toast(error.message || "Could not refresh router state", "bad");
    } finally {
      $("#refreshBtn").classList.remove("is-loading");
    }
  }

  function wireStaticActions() {
    document.addEventListener("click", async (event) => {
      const nav = event.target.closest(".nav");
      if (nav) {
        setView(nav.dataset.view);
        return;
      }

      const jump = event.target.closest("[data-view-jump]");
      if (jump) {
        setView(jump.dataset.viewJump);
        return;
      }

      const accordion = event.target.closest(".route-accordion-item");
      if (accordion) {
        document.querySelectorAll(".route-accordion-item").forEach((item) =>
          item.classList.toggle("active", item === accordion),
        );
        return;
      }

      const save = event.target.closest(".setup-save");
      if (save) {
        const key = save.dataset.key;
        const input = document.querySelector(
          `[data-setup-input="${CSS.escape(key)}"]`,
        );
        const value = input?.value?.trim();
        if (!value) {
          toast("Enter a value first", "neutral");
          return;
        }
        const original = save.textContent;
        save.textContent = "Saving…";
        save.disabled = true;
        try {
          await api("/api/setup/value", {
            method: "POST",
            body: JSON.stringify({ key, value }),
          });
          input.value = "";
          toast("Provider setting saved", "good");
          await refresh();
        } catch (error) {
          toast(error.message || "Could not save setting", "bad");
        } finally {
          save.textContent = original;
          save.disabled = false;
        }
        return;
      }

      const remove = event.target.closest(".setup-remove");
      if (remove) {
        const key = remove.dataset.key;
        const original = remove.textContent;
        remove.textContent = "Removing…";
        remove.disabled = true;
        try {
          await api(`/api/setup/value/${encodeURIComponent(key)}`, {
            method: "DELETE",
          });
          toast("Local value removed", "good");
          await refresh();
        } catch (error) {
          toast(error.message || "Could not remove setting", "bad");
        } finally {
          remove.textContent = original;
          remove.disabled = false;
        }
        return;
      }

      const probe = event.target.closest(".certify");
      if (probe) {
        await certify(probe.dataset.provider, probe);
        return;
      }

      const quotaButton = event.target.closest(".quota-refresh");
      if (quotaButton) {
        await refreshQuota(quotaButton.dataset.provider, quotaButton);
        return;
      }

      const trace = event.target.closest(".trace-link");
      if (trace) {
        await loadTrace(trace.dataset.request);
        return;
      }

      const routeCopy = event.target.closest(".route-copy");
      if (routeCopy) {
        await copyText(routeCopy.dataset.model || "", "Route model copied");
        return;
      }

      const routeDelete = event.target.closest(".route-delete");
      if (routeDelete) {
        routeDelete.disabled = true;
        try {
          await api(`/api/routes/${encodeURIComponent(routeDelete.dataset.route)}`, {
            method: "DELETE",
          });
          toast("Route profile deleted", "good");
          await refresh();
        } catch (error) {
          toast(error.message || "Could not delete route", "bad");
        } finally {
          routeDelete.disabled = false;
        }
        return;
      }

      const projectDelete = event.target.closest(".project-delete");
      if (projectDelete) {
        projectDelete.disabled = true;
        try {
          await api(`/api/projects/${encodeURIComponent(projectDelete.dataset.project)}`, {
            method: "DELETE",
          });
          if (projectKey().startsWith(projectDelete.dataset.prefix || "__never__")) {
            window.sessionStorage.removeItem("routerProjectKey");
          }
          toast("Project key revoked", "good");
          await refresh();
        } catch (error) {
          toast(error.message || "Could not revoke project", "bad");
        } finally {
          projectDelete.disabled = false;
        }
        return;
      }
    });

    $("#refreshBtn").addEventListener("click", refresh);
    $("#providerSearch").addEventListener("input", renderProviders);
    $("#tierFilter").addEventListener("change", renderProviders);

    $("#copyBase").addEventListener("click", () =>
      copyText(`${location.origin}/v1`, "Base URL copied"),
    );

    $("#adminUnlockBtn").addEventListener("click", () => {
      $("#adminKeyInput").value = adminKey();
      $("#adminDialog").showModal();
    });

    $("#saveAdminKey").addEventListener("click", async () => {
      const value = $("#adminKeyInput").value.trim();
      if (!value) {
        toast("Enter the admin key or clear it", "neutral");
        return;
      }
      window.sessionStorage.setItem("routerAdminKey", value);
      $("#adminDialog").close();
      toast("Admin controls unlocked for this tab", "good");
      await refresh();
    });

    $("#clearAdminKey").addEventListener("click", async () => {
      window.sessionStorage.removeItem("routerAdminKey");
      $("#adminKeyInput").value = "";
      $("#adminDialog").close();
      toast("Session admin key cleared", "neutral");
      await refresh();
    });

    $$(".snippet-tab").forEach((button) =>
      button.addEventListener("click", () => {
        state.activeSnippet = button.dataset.snippet;
        renderSnippet();
      }),
    );

    $("#copySnippet").addEventListener("click", () =>
      copyText($("#snippetCode").textContent, "Snippet copied"),
    );

    $("#saveRoute").addEventListener("click", async () => {
      const button = $("#saveRoute");
      const slug = $("#routeSlug").value.trim().toLowerCase();
      const name = $("#routeName").value.trim();
      if (!slug || !name) {
        toast("Route name and slug are required", "neutral");
        return;
      }

      const splitProviders = (value) =>
        value
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);

      const context = Number($("#routeContext").value || 0);
      const fallbacks = Number($("#routeFallbacks").value || 8);
      button.disabled = true;
      try {
        await api("/api/routes", {
          method: "POST",
          body: JSON.stringify({
            slug,
            name,
            base_route: $("#routeBase").value,
            providers_allow: splitProviders($("#routeAllow").value),
            providers_deny: splitProviders($("#routeDeny").value),
            min_context: context > 0 ? context : null,
            max_fallbacks: fallbacks,
            allow_promo: $("#routePromo").checked,
            allow_trial: $("#routeTrial").checked,
            enabled: true,
          }),
        });
        ["#routeName", "#routeSlug", "#routeAllow", "#routeDeny", "#routeContext"].forEach(
          (selector) => {
            $(selector).value = "";
          },
        );
        $("#routeFallbacks").value = "8";
        $("#routePromo").checked = false;
        $("#routeTrial").checked = false;
        toast(`route/${slug} saved`, "good");
        await refresh();
      } catch (error) {
        toast(error.message || "Could not save route", "bad");
      } finally {
        button.disabled = false;
      }
    });

    $("#copyProjectKey").addEventListener("click", () => {
      const value = $("#newProjectKeyValue").textContent;
      if (value) copyText(value, "Project key copied");
    });

    $("#createProject").addEventListener("click", async () => {
      const button = $("#createProject");
      const name = $("#projectName").value.trim();
      if (!name) {
        toast("Enter a project name", "neutral");
        return;
      }

      const requests = Number($("#projectRequestLimit").value || 0);
      const tokens = Number($("#projectTokenLimit").value || 0);
      button.disabled = true;
      try {
        const created = await api("/api/projects", {
          method: "POST",
          body: JSON.stringify({
            name,
            daily_request_limit: requests > 0 ? requests : null,
            daily_token_limit: tokens > 0 ? tokens : null,
          }),
        });
        state.newProjectKey = created.key;
        window.sessionStorage.setItem("routerProjectKey", created.key);
        $("#newProjectKeyValue").textContent = created.key;
        $("#newProjectKey").hidden = false;
        $("#projectName").value = "";
        $("#projectRequestLimit").value = "";
        $("#projectTokenLimit").value = "";
        toast("Project key created and attached to this tab — copy it now", "good");
        await refresh();
      } catch (error) {
        toast(error.message || "Could not create project", "bad");
      } finally {
        button.disabled = false;
      }
    });

    $("#exportConfig").addEventListener("click", async () => {
      try {
        const payload = await api("/api/config/export");
        const blob = new Blob([JSON.stringify(payload, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "the-router-config.json";
        link.click();
        URL.revokeObjectURL(url);
        toast("Config exported without secret values", "good");
      } catch (error) {
        toast(error.message || "Could not export config", "bad");
      }
    });

    $("#importConfig").addEventListener("click", () => {
      $("#importConfigFile").click();
    });

    $("#importConfigFile").addEventListener("change", async (event) => {
      const file = event.target.files?.[0];
      if (!file) return;
      try {
        const payload = JSON.parse(await file.text());
        const result = await api("/api/config/import", {
          method: "POST",
          body: JSON.stringify({
            version: payload.version || 1,
            settings: payload.settings || {},
          }),
        });
        toast(`${result.settings_imported || 0} settings imported`, "good");
        await refresh();
      } catch (error) {
        toast(error.message || "Could not import config", "bad");
      } finally {
        event.target.value = "";
      }
    });

    $("#previewRoute").addEventListener("click", async () => {
      const box = $("#routePreview");
      box.innerHTML = '<div class="sub">Scoring candidates…</div>';
      try {
        const result = await api("/api/route/preview", {
          method: "POST",
          body: JSON.stringify(playgroundRequest()),
        });
        box.innerHTML =
          (result.candidates || [])
            .slice(0, 6)
            .map(
              (candidate, index) => `
                <div class="route-chip">
                  <div>
                    <span>${index + 1}. ${esc(candidate.provider_id)}/${esc(candidate.model_id)}</span>
                    <small>${esc(candidate.reason)}</small>
                  </div>
                  <b>${Number(candidate.score).toFixed(3)}</b>
                </div>
              `,
            )
            .join("") ||
          '<div class="empty-state">No eligible candidate. Add a provider key or choose another pool.</div>';
      } catch (error) {
        box.innerHTML = `<div class="err">${esc(error.message)}</div>`;
      }
    });

    $("#sendPrompt").addEventListener("click", async () => {
      const output = $("#playOutput");
      const meta = $("#routeMeta");
      const button = $("#sendPrompt");
      output.textContent = "Routing…";
      meta.textContent = "";
      button.disabled = true;

      try {
        const response = await fetch("/v1/chat/completions", {
          method: "POST",
          headers: inferenceHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(playgroundRequest()),
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || JSON.stringify(data));
        }

        const result =
          data.choices?.[0]?.message?.content ?? JSON.stringify(data, null, 2);
        output.textContent =
          typeof result === "string" ? result : JSON.stringify(result, null, 2);

        const provider =
          response.headers.get("x-router-provider") || data.router?.provider || "router";
        const model =
          response.headers.get("x-router-model") || data.router?.model || "unknown";
        const fallback =
          response.headers.get("x-router-fallback-count") ||
          data.router?.fallback_count ||
          0;
        meta.textContent = `${provider} / ${model} · fallback ${fallback}`;

        await refresh();
        if (data.router?.request_id) {
          await loadTrace(data.router.request_id);
        }
      } catch (error) {
        output.textContent = error.message;
        meta.textContent = "Request failed";
        toast(error.message || "Playground request failed", "bad");
      } finally {
        button.disabled = false;
      }
    });
  }

  let liveSource = null;
  let liveRefreshTimer = null;

  function startLiveEvents() {
    if (!("EventSource" in window) || liveSource) return;
    liveSource = new EventSource("/api/events");
    liveSource.addEventListener("usage", () => {
      window.clearTimeout(liveRefreshTimer);
      liveRefreshTimer = window.setTimeout(() => {
        refresh();
      }, 500);
    });
    liveSource.onerror = () => {
      // EventSource reconnects automatically. Manual refresh remains available.
    };
  }

  function boot() {
    $("#baseUrl").textContent = `${location.origin}/v1`;
    wireStaticActions();

    const initialView = location.hash.replace("#", "");
    if (VIEW_META[initialView]) {
      setView(initialView);
    }

    refresh().then(startLiveEvents);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
