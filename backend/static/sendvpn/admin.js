"use strict";

const tg = window.Telegram?.WebApp;

const state = {
  me: null,
  users: { items: [], total: 0, query: "", filter: "all", selected: new Set() },
  payments: [],
  broadcasts: [],
  log: [],
  config: null,
  stats: null,
  activeSection: "dashboard",
};

function $(id) { return document.getElementById(id); }
function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function showToast(message, isError) {
  const node = $("adminToast");
  if (!node) return;
  node.textContent = message;
  node.classList.toggle("error", Boolean(isError));
  node.classList.add("show");
  clearTimeout(node._t);
  node._t = setTimeout(() => node.classList.remove("show"), 2400);
}

async function api(path, options = {}) {
  const init = {
    credentials: "same-origin",
    method: "GET",
    headers: { "Content-Type": "application/json" },
    ...options,
  };
  if (init.body && typeof init.body !== "string") {
    init.body = JSON.stringify(init.body);
  }
  const response = await fetch(path, init);
  const text = await response.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; }
  catch { throw new Error("Сервер вернул не-JSON"); }
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || data.detail || `HTTP ${response.status}`);
  }
  return data;
}

async function authenticate() {
  const status = $("adminLoadingStatus");
  status.textContent = "Передаём initData…";
  if (tg?.initData) {
    try {
      await api("/api/auth/telegram-webapp", {
        method: "POST",
        body: { initData: tg.initData, init_data: tg.initData },
      });
    } catch (error) {
      // Outside of telegram or auth fails — still try to read /api/admin/me below.
      console.warn("auth failed", error);
    }
  }
  status.textContent = "Проверяем права…";
  const me = await api("/api/admin/me");
  if (!me.is_admin) {
    document.body.innerHTML = `
      <div class="admin-forbidden">
        <div>
          <h1>Доступ закрыт</h1>
          <p>Эта панель доступна только админам SendVPN. Если вы должны иметь доступ — попросите выдать вам админ-права.</p>
          <p style="margin-top:14px">Ваш ID: <code>${escapeHtml(me.tg_id ?? "—")}</code></p>
        </div>
      </div>`;
    return false;
  }
  state.me = me;
  return true;
}

function setSection(name) {
  state.activeSection = name;
  document.querySelectorAll(".admin-nav button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.section === name);
  });
  document.querySelectorAll(".admin-section").forEach((section) => {
    section.classList.toggle("hidden", section.dataset.section !== name);
  });
  switch (name) {
    case "dashboard": refreshDashboard(); break;
    case "users": refreshUsers(); break;
    case "payments": refreshPayments(); break;
    case "broadcasts": refreshBroadcasts(); break;
    case "tariffs": refreshTariffs(); break;
    case "config": refreshConfig(); break;
    case "log": refreshLog(); break;
    case "tools": /* static UI */ break;
    case "analytics": refreshAnalytics(); break;
    case "events": refreshEvents(); break;
    case "promos": refreshPromos(); break;
    case "backup": /* static UI */ break;
  }
  // Auto-collapse mobile nav after navigation
  document.getElementById("adminNav")?.classList.remove("open");
}

function fmtRub(amount) {
  return `${Number(amount || 0).toLocaleString("ru-RU")} ₽`;
}

function fmtTs(ts) {
  if (!ts) return "—";
  return new Date(Number(ts) * 1000).toLocaleString("ru-RU");
}

async function refreshDashboard() {
  const grid = $("kpiGrid");
  grid.innerHTML = `<div class="kpi-card"><div class="kpi-label">Загрузка…</div></div>`;
  try {
    const stats = await api("/api/admin/stats");
    state.stats = stats;
    const items = [
      { label: "Всего юзеров", value: stats.users_total, sub: `${stats.users_active} активных` },
      { label: "Активные подписки", value: stats.users_active, sub: `+${stats.users_trial} триал` },
      { label: "Заблокировано", value: stats.users_banned, sub: "ban" },
      { label: "Платежи", value: stats.payments_total, sub: `${stats.payments_pending} в очереди` },
      { label: "Доход", value: fmtRub(stats.revenue_rub), sub: "оплаченные" },
      { label: "Рассылки", value: stats.broadcasts_total, sub: "всего" },
      { label: "Сайт", value: stats.config_locked ? "Заблокирован" : "Открыт", sub: stats.config_locked ? "lock" : "OK" },
      { label: "Сейчас", value: fmtTs(stats.now), sub: "UTC" },
    ];
    grid.innerHTML = items.map((it) => `
      <div class="kpi-card">
        <div class="kpi-label">${escapeHtml(it.label)}</div>
        <div class="kpi-value">${escapeHtml(it.value)}</div>
        <div class="kpi-sub">${escapeHtml(it.sub)}</div>
      </div>`).join("");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function refreshUsers() {
  const tbody = $("usersTbody");
  tbody.innerHTML = `<tr><td colspan="7">Загрузка…</td></tr>`;
  try {
    let url;
    const filter = state.users.filter;
    if (filter === "active") url = "/api/admin/users/active";
    else if (filter === "banned") url = "/api/admin/users/banned";
    else if (filter === "expiring") url = "/api/admin/users/expiring?days=3";
    else if (filter === "inactive") url = "/api/admin/users/inactive?days=14";
    else {
      const params = new URLSearchParams();
      if (state.users.query) params.set("q", state.users.query);
      url = `/api/admin/users?${params}`;
    }
    const data = await api(url);
    let items = data.items || [];
    if (filter === "trial") items = items.filter((u) => u.free_used && !u.has_subscription);
    state.users = { ...state.users, items, total: data.total ?? items.length };
    $("usersMeta").textContent = `Показано ${items.length} из ${state.users.total}`;
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="7">Пусто. Кнопка «Сгенерировать demo-пользователей» на дашборде создаст пробных.</td></tr>`;
      return;
    }
    tbody.innerHTML = items.map((u) => userRow(u)).join("");
    updateBulkBar();
  } catch (error) {
    tbody.innerHTML = `<tr><td colspan="7">${escapeHtml(error.message)}</td></tr>`;
  }
}

function avatarHtml(user) {
  if (user.photo_url) {
    return `<div class="user-avatar"><img src="${escapeHtml(user.photo_url)}" alt=""></div>`;
  }
  const letter = (user.name || user.username || "?").trim().charAt(0).toUpperCase() || "?";
  return `<div class="user-avatar">${escapeHtml(letter)}</div>`;
}

function userRow(user) {
  const tags = [];
  if (user.is_admin) tags.push(`<span class="tag info">admin</span>`);
  if (user.banned) tags.push(`<span class="tag danger">ban</span>`);
  if (user.has_subscription) tags.push(`<span class="tag ok">active</span>`);
  else tags.push(`<span class="tag">offline</span>`);
  if (user.free_used && !user.has_subscription) tags.push(`<span class="tag warn">trial used</span>`);
  const checked = state.users.selected.has(user.tg_id) ? "checked" : "";
  return `
    <tr data-uid="${user.tg_id}">
      <td><input type="checkbox" class="user-check" data-uid="${user.tg_id}" ${checked}></td>
      <td data-action="open">
        <div class="user-cell">
          ${avatarHtml(user)}
          <div>
            <div class="user-name">${escapeHtml(user.name || "—")}</div>
            <div class="user-meta">@${escapeHtml(user.username || "—")} · ${user.tg_id}</div>
          </div>
        </div>
      </td>
      <td data-action="open">${escapeHtml(user.tariff_name || "—")}</td>
      <td data-action="open">${user.days_left || 0}</td>
      <td data-action="open">${fmtRub(user.balance)}</td>
      <td data-action="open">${tags.join(" ")}</td>
      <td><button class="admin-btn small" data-action="open">Открыть</button></td>
    </tr>`;
}

function updateBulkBar() {
  const bar = $("bulkBar");
  const count = state.users.selected.size;
  if (!bar) return;
  bar.classList.toggle("hidden", count === 0);
  $("bulkCount").textContent = `${count} выбрано`;
}

function openUser(uid) {
  const user = state.users.items.find((u) => u.tg_id === uid);
  if (!user) return;
  $("drawerName").textContent = user.name || "—";
  $("drawerId").textContent = `@${user.username || "—"} · ${user.tg_id}`;
  const subUrl = user.sub_url || "—";
  $("drawerBody").innerHTML = `
    <dl class="kv-grid">
      <dt>Telegram ID</dt><dd>${user.tg_id}</dd>
      <dt>Username</dt><dd>@${escapeHtml(user.username || "—")}</dd>
      <dt>Язык</dt><dd>${escapeHtml(user.language_code || "—")}</dd>
      <dt>Premium</dt><dd>${user.is_premium ? "да" : "нет"}</dd>
      <dt>Создан</dt><dd>${fmtTs(user.created_at)}</dd>
      <dt>Активность</dt><dd>${fmtTs(user.last_seen)}</dd>
      <dt>Тариф</dt><dd>${escapeHtml(user.tariff_name || "—")} · ${user.days_left || 0} дн.</dd>
      <dt>До</dt><dd>${escapeHtml(user.expires_human || "—")}</dd>
      <dt>Устройства</dt><dd>${user.devices_active}/${user.devices_max}</dd>
      <dt>Баланс</dt><dd>${fmtRub(user.balance)}</dd>
      <dt>Sub URL</dt><dd>${escapeHtml(subUrl)}</dd>
      <dt>Sub UUID</dt><dd>${escapeHtml(user.sub_uuid || "—")}</dd>
      <dt>HMAC</dt><dd>${user.verified ? "verified" : "unverified"}</dd>
    </dl>
    <div class="action-grid">
      <button class="admin-btn primary" data-act="grant">+30 дней</button>
      <button class="admin-btn" data-act="grant3">+3 дня</button>
      <button class="admin-btn" data-act="grant_custom">+ N дней…</button>
      <button class="admin-btn" data-act="balance_add">Баланс +500</button>
      <button class="admin-btn" data-act="balance_set">Установить баланс…</button>
      <button class="admin-btn" data-act="regen">Обновить sub-uuid</button>
      <button class="admin-btn" data-act="reset_trial">Сбросить триал</button>
      <button class="admin-btn" data-act="clear_devices">Очистить устройства</button>
      <button class="admin-btn ${user.banned ? "" : "warn"}" data-act="${user.banned ? "unban" : "ban"}">${user.banned ? "Разбанить" : "Забанить"}</button>
      <button class="admin-btn" data-act="${user.is_admin ? "demote" : "promote"}">${user.is_admin ? "Снять админа" : "Сделать админом"}</button>
      <button class="admin-btn" data-act="revoke">Снять подписку</button>
      <button class="admin-btn danger" data-act="delete">Удалить</button>
    </div>`;
  $("userDrawer").classList.remove("hidden");
  $("userDrawer").dataset.uid = String(uid);
}

function closeUser() {
  $("userDrawer").classList.add("hidden");
}

async function userAction(uid, action) {
  try {
    let result;
    switch (action) {
      case "grant": result = await api(`/api/admin/users/${uid}/grant-days`, { method: "POST", body: { days: 30, tariff_name: "Премиум" } }); break;
      case "grant3": result = await api(`/api/admin/users/${uid}/grant-days`, { method: "POST", body: { days: 3, tariff_name: "Бонус" } }); break;
      case "grant_custom": {
        const raw = prompt("Сколько дней добавить?");
        const days = Number(raw);
        if (!days) return;
        result = await api(`/api/admin/users/${uid}/grant-days`, { method: "POST", body: { days, tariff_name: "Админ" } });
        break;
      }
      case "balance_add": result = await api(`/api/admin/users/${uid}/balance`, { method: "POST", body: { delta: 500 } }); break;
      case "balance_set": {
        const raw = prompt("Установить баланс (₽):");
        if (raw === null) return;
        result = await api(`/api/admin/users/${uid}/balance`, { method: "POST", body: { set: Number(raw) || 0 } });
        break;
      }
      case "regen": result = await api(`/api/admin/users/${uid}/regen-sub`, { method: "POST", body: {} }); break;
      case "reset_trial": result = await api(`/api/admin/users/${uid}/reset-trial`, { method: "POST", body: {} }); break;
      case "clear_devices": result = await api(`/api/admin/users/${uid}/devices/clear`, { method: "POST", body: {} }); break;
      case "ban": result = await api(`/api/admin/users/${uid}/ban`, { method: "POST", body: {} }); break;
      case "unban": result = await api(`/api/admin/users/${uid}/unban`, { method: "POST", body: {} }); break;
      case "promote": result = await api(`/api/admin/users/${uid}/promote`, { method: "POST", body: {} }); break;
      case "demote": result = await api(`/api/admin/users/${uid}/demote`, { method: "POST", body: {} }); break;
      case "revoke": if (!confirm("Снять подписку?")) return; result = await api(`/api/admin/users/${uid}/revoke`, { method: "POST", body: {} }); break;
      case "delete": if (!confirm("Удалить пользователя НАВСЕГДА?")) return; await api(`/api/admin/users/${uid}/delete`, { method: "POST", body: {} }); closeUser(); refreshUsers(); showToast("Удалено"); return;
      default: return;
    }
    showToast("OK");
    if (result?.user) {
      const idx = state.users.items.findIndex((u) => u.tg_id === uid);
      if (idx >= 0) state.users.items[idx] = result.user;
      openUser(uid);
      refreshUsers();
    }
  } catch (error) {
    showToast(error.message, true);
  }
}

async function refreshPayments() {
  const tbody = $("paymentsTbody");
  tbody.innerHTML = `<tr><td colspan="7">Загрузка…</td></tr>`;
  try {
    const data = await api("/api/admin/payments");
    state.payments = data.items;
    if (!data.items.length) {
      tbody.innerHTML = `<tr><td colspan="7">Платежей нет</td></tr>`;
      return;
    }
    tbody.innerHTML = data.items.map((p) => `
      <tr>
        <td><code>${escapeHtml(p.id)}</code></td>
        <td>${p.tg_id}</td>
        <td>${escapeHtml(p.tariff || "—")}</td>
        <td>${fmtRub(p.amount)}</td>
        <td>${escapeHtml(p.provider || "—")}</td>
        <td><span class="tag ${p.status === "paid" ? "ok" : p.status === "rejected" ? "danger" : "warn"}">${escapeHtml(p.status)}</span></td>
        <td>
          <button class="admin-btn small primary" data-pay-approve="${escapeHtml(p.id)}" ${p.status !== "pending" ? "disabled" : ""}>OK</button>
          <button class="admin-btn small warn" data-pay-reject="${escapeHtml(p.id)}" ${p.status !== "pending" ? "disabled" : ""}>×</button>
        </td>
      </tr>`).join("");
  } catch (error) {
    tbody.innerHTML = `<tr><td colspan="7">${escapeHtml(error.message)}</td></tr>`;
  }
}

async function refreshBroadcasts() {
  const tbody = $("broadcastsTbody");
  tbody.innerHTML = `<tr><td colspan="5">Загрузка…</td></tr>`;
  try {
    const data = await api("/api/admin/broadcasts");
    state.broadcasts = data.items;
    if (!data.items.length) {
      tbody.innerHTML = `<tr><td colspan="5">Пока пусто</td></tr>`;
      return;
    }
    tbody.innerHTML = data.items.map((b) => `
      <tr>
        <td><code>${escapeHtml(b.id)}</code></td>
        <td>${fmtTs(b.ts)}</td>
        <td>${escapeHtml(b.target)}</td>
        <td>${b.recipients_count} → ${b.sent_count ?? 0} ✓ / ${b.failed_count ?? 0} ×</td>
        <td><span class="tag ${b.status === "sent" ? "ok" : b.status === "failed" ? "danger" : "warn"}">${escapeHtml(b.status)}</span></td>
      </tr>`).join("");
  } catch (error) {
    tbody.innerHTML = `<tr><td colspan="5">${escapeHtml(error.message)}</td></tr>`;
  }
}

async function refreshTariffs() {
  const editor = $("tariffEditor");
  editor.innerHTML = "Загрузка…";
  try {
    const data = await api("/api/admin/config");
    state.config = data.config;
    renderTariffEditor();
  } catch (error) {
    editor.innerHTML = `<div>${escapeHtml(error.message)}</div>`;
  }
}

function renderTariffEditor() {
  const editor = $("tariffEditor");
  const tariffs = state.config?.tariffs || [];
  editor.innerHTML = tariffs.map((t, idx) => `
    <div class="tariff-row" data-idx="${idx}">
      <label class="admin-field"><span>Ключ</span><input class="admin-input" data-field="key" value="${escapeHtml(t.key || "")}"></label>
      <label class="admin-field"><span>Название</span><input class="admin-input" data-field="name" value="${escapeHtml(t.name || "")}"></label>
      <label class="admin-field"><span>Дней</span><input class="admin-input" type="number" data-field="days" value="${t.days || 0}"></label>
      <label class="admin-field"><span>Устройств</span><input class="admin-input" type="number" data-field="devices" value="${t.devices || 0}"></label>
      <label class="admin-field"><span>Цена ₽</span><input class="admin-input" type="number" data-field="price_rub" value="${t.price_rub || 0}"></label>
      <button class="admin-btn warn" data-action="remove">×</button>
    </div>`).join("");
}

async function saveTariffs() {
  const rows = document.querySelectorAll("#tariffEditor .tariff-row");
  const tariffs = [];
  rows.forEach((row) => {
    const inputs = row.querySelectorAll("input");
    const obj = {};
    inputs.forEach((input) => {
      const v = input.value;
      obj[input.dataset.field] = input.type === "number" ? Number(v) : v;
    });
    if (obj.key) tariffs.push(obj);
  });
  try {
    const data = await api("/api/admin/tariffs", { method: "POST", body: { tariffs } });
    state.config.tariffs = data.tariffs;
    showToast("Тарифы сохранены");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function refreshConfig() {
  try {
    const data = await api("/api/admin/config");
    state.config = data.config;
    $("cfgBot").value = data.config.bot_username || "";
    $("cfgChannel").value = data.config.channel_url || "";
    $("cfgSupport").value = data.config.support_url || "";
    $("cfgExtraDevice").value = data.config.extra_device_rub || 0;
    $("cfgTrialDays").value = data.config.free_trial_days || 0;
    $("cfgRefDays").value = data.config.referral_trial_bonus_days || 0;
    $("cfgRefPercent").value = data.config.referral_purchase_percent || 0;
    $("cfgProvSbp").checked = !!data.config.providers?.sbp;
    $("cfgProvCard").checked = !!data.config.providers?.card;
    $("cfgProvCrypto").checked = !!data.config.providers?.crypto;
    $("cfgProvBalance").checked = !!data.config.providers?.balance;
    $("cfgLocked").checked = !!data.config.site_locked;
    $("cfgLockMsg").value = data.config.site_locked_message || "";
    if ($("cfgStarsRub")) $("cfgStarsRub").value = data.config.stars_rate_rub ?? 1.39;
    if ($("cfgStarsUsd")) $("cfgStarsUsd").value = data.config.stars_rate_usd ?? 0.013;
    if ($("cfgUsdRub")) $("cfgUsdRub").value = data.config.usd_rate_rub ?? 0.011;
    if ($("cfgStarsPacks")) $("cfgStarsPacks").value = (data.config.stars_packs || []).join(",");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function saveConfig() {
  const body = {
    bot_username: $("cfgBot").value,
    channel_url: $("cfgChannel").value,
    support_url: $("cfgSupport").value,
    extra_device_rub: Number($("cfgExtraDevice").value) || 0,
    free_trial_days: Number($("cfgTrialDays").value) || 0,
    referral_trial_bonus_days: Number($("cfgRefDays").value) || 0,
    referral_purchase_percent: Number($("cfgRefPercent").value) || 0,
    providers: {
      sbp: $("cfgProvSbp").checked,
      card: $("cfgProvCard").checked,
      crypto: $("cfgProvCrypto").checked,
      balance: $("cfgProvBalance").checked,
    },
    site_locked: $("cfgLocked").checked,
    site_locked_message: $("cfgLockMsg").value,
    stars_rate_rub: Number($("cfgStarsRub")?.value) || 1.39,
    stars_rate_usd: Number($("cfgStarsUsd")?.value) || 0.013,
    usd_rate_rub: Number($("cfgUsdRub")?.value) || 0.011,
    stars_packs: ($("cfgStarsPacks")?.value || "").split(",").map((s) => Number(s.trim())).filter(Boolean),
  };
  try {
    await api("/api/admin/config", { method: "POST", body });
    showToast("Конфиг сохранён");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function refreshLog() {
  const tbody = $("logTbody");
  tbody.innerHTML = `<tr><td colspan="5">Загрузка…</td></tr>`;
  try {
    const data = await api("/api/admin/log");
    state.log = data.items;
    if (!data.items.length) {
      tbody.innerHTML = `<tr><td colspan="5">Журнал пуст</td></tr>`;
      return;
    }
    tbody.innerHTML = data.items.map((l) => `
      <tr>
        <td>${fmtTs(l.ts)}</td>
        <td>${l.actor}</td>
        <td><code>${escapeHtml(l.action)}</code></td>
        <td>${l.target ?? "—"}</td>
        <td><code style="font-size:0.7rem">${escapeHtml(JSON.stringify(l.payload || {}))}</code></td>
      </tr>`).join("");
  } catch (error) {
    tbody.innerHTML = `<tr><td colspan="5">${escapeHtml(error.message)}</td></tr>`;
  }
}

async function quickAction(name) {
  try {
    if (name === "seed") {
      const data = await api("/api/admin/seed-demo", { method: "POST", body: {} });
      showToast(`Создано: ${data.created.length}`);
      if (state.activeSection === "users") refreshUsers();
      else refreshDashboard();
    }
    if (name === "goto-users") setSection("users");
    if (name === "goto-broadcast") setSection("broadcasts");
    if (name === "lock-toggle") {
      const cfg = state.config || (await api("/api/admin/config")).config;
      const next = !cfg.site_locked;
      await api("/api/admin/lock", { method: "POST", body: { locked: next, message: cfg.site_locked_message || "Идут технические работы" } });
      showToast(next ? "Сайт заблокирован" : "Сайт открыт");
      refreshDashboard();
    }
  } catch (error) {
    showToast(error.message, true);
  }
}

async function sendBroadcast() {
  const text = $("broadcastText").value.trim();
  const target = $("broadcastTarget").value;
  if (!text) { showToast("Введите сообщение", true); return; }
  try {
    await api("/api/admin/broadcast", { method: "POST", body: { text, target } });
    $("broadcastText").value = "";
    showToast("Поставлено в очередь");
    refreshBroadcasts();
  } catch (error) {
    showToast(error.message, true);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    if (tg?.expand) tg.expand();
    if (tg?.ready) tg.ready();
    if (tg?.setHeaderColor) tg.setHeaderColor("#060606");
    if (tg?.setBackgroundColor) tg.setBackgroundColor("#060606");
  } catch {}

  if (!await authenticate()) return;

  $("adminLoading").classList.add("hidden");
  $("adminShell").classList.remove("hidden");
  $("adminActor").textContent = `${state.me.tg_id} · admin`;

  document.querySelectorAll(".admin-nav button").forEach((btn) => {
    btn.addEventListener("click", () => setSection(btn.dataset.section));
  });
  document.querySelectorAll(".quick-actions [data-quick]").forEach((btn) => {
    btn.addEventListener("click", () => quickAction(btn.dataset.quick));
  });

  $("dashRefresh").addEventListener("click", refreshDashboard);
  $("usersRefresh").addEventListener("click", refreshUsers);
  $("usersSearch").addEventListener("input", (e) => {
    state.users.query = e.target.value;
    clearTimeout(state.users._t);
    state.users._t = setTimeout(refreshUsers, 250);
  });
  $("paymentsRefresh").addEventListener("click", refreshPayments);
  $("broadcastsRefresh").addEventListener("click", refreshBroadcasts);
  $("broadcastSend").addEventListener("click", sendBroadcast);
  $("tariffSave").addEventListener("click", saveTariffs);
  $("tariffAdd").addEventListener("click", () => {
    state.config.tariffs.push({ key: `t${Date.now()}`, name: "Новый", days: 30, devices: 3, price_rub: 100 });
    renderTariffEditor();
  });
  $("configSave").addEventListener("click", saveConfig);
  $("logRefresh").addEventListener("click", refreshLog);
  $("drawerClose").addEventListener("click", closeUser);

  $("usersTbody").addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-uid]");
    if (!row) return;
    const uid = Number(row.dataset.uid);
    if (event.target.matches(".user-check")) {
      if (event.target.checked) state.users.selected.add(uid);
      else state.users.selected.delete(uid);
      updateBulkBar();
      return;
    }
    if (event.target.closest("[data-action]")) openUser(uid);
  });
  $("usersSelectAll")?.addEventListener("change", (event) => {
    const checked = event.target.checked;
    state.users.items.forEach((u) => {
      if (checked) state.users.selected.add(u.tg_id);
      else state.users.selected.delete(u.tg_id);
    });
    document.querySelectorAll("#usersTbody .user-check").forEach((cb) => { cb.checked = checked; });
    updateBulkBar();
  });
  document.querySelectorAll("#userFilters [data-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#userFilters [data-filter]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.users.filter = btn.dataset.filter;
      state.users.selected.clear();
      refreshUsers();
    });
  });
  $("bulkBar")?.addEventListener("click", async (event) => {
    const action = event.target.dataset.bulk;
    if (!action) return;
    const ids = Array.from(state.users.selected);
    if (action === "clear") { state.users.selected.clear(); refreshUsers(); return; }
    if (!ids.length) { showToast("Никто не выбран", true); return; }
    try {
      if (action === "ban") await api("/api/admin/users/bulk/ban", { method: "POST", body: { tg_ids: ids } });
      else if (action === "unban") await api("/api/admin/users/bulk/unban", { method: "POST", body: { tg_ids: ids } });
      else if (action === "regen") await api("/api/admin/users/bulk/regen-sub", { method: "POST", body: { tg_ids: ids } });
      else if (action === "revoke") {
        if (!confirm(`Снять подписку у ${ids.length} юзеров?`)) return;
        await api("/api/admin/users/bulk/revoke", { method: "POST", body: { tg_ids: ids } });
      } else if (action === "delete") {
        if (!confirm(`УДАЛИТЬ ${ids.length} юзеров навсегда?`)) return;
        await api("/api/admin/users/bulk/delete", { method: "POST", body: { tg_ids: ids } });
      } else if (action === "grant") {
        const raw = prompt("Сколько дней добавить?", "7");
        const days = Number(raw);
        if (!days) return;
        await api("/api/admin/users/bulk/grant-days", { method: "POST", body: { tg_ids: ids, days } });
      } else if (action === "balance-add") {
        const raw = prompt("На сколько ₽ изменить баланс? (можно отрицательное)", "100");
        const delta = Number(raw);
        if (!delta) return;
        await api("/api/admin/users/bulk/balance", { method: "POST", body: { tg_ids: ids, delta } });
      } else if (action === "balance-set") {
        const raw = prompt("Установить баланс ₽:", "0");
        if (raw === null) return;
        await api("/api/admin/users/bulk/balance", { method: "POST", body: { tg_ids: ids, set: Number(raw) || 0 } });
      }
      state.users.selected.clear();
      refreshUsers();
      showToast(`OK · ${ids.length}`);
    } catch (error) { showToast(error.message, true); }
  });
  document.querySelectorAll("[data-tool]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const tool = btn.dataset.tool;
      const out = $("toolOutput");
      const log = (text) => { if (out) out.textContent = text; };
      try {
        if (tool === "seed") {
          const data = await api("/api/admin/seed-demo", { method: "POST", body: {} });
          showToast(`Создано: ${data.created.length}`); log(JSON.stringify(data, null, 2));
        } else if (tool === "clear-expired") {
          if (!confirm("Снять подписку у всех с истёкшим сроком?")) return;
          const data = await api("/api/admin/maintenance/clear-expired", { method: "POST", body: {} });
          showToast(`Снято: ${data.cleared}`); log(JSON.stringify(data, null, 2));
        } else if (tool === "regen-uuids") {
          if (!confirm("Регенерировать sub-uuid у ВСЕХ юзеров? Все ссылки подписок изменятся.")) return;
          const data = await api("/api/admin/maintenance/regen-all-uuids", { method: "POST", body: {} });
          showToast(`Обновлено: ${data.regenerated}`); log(JSON.stringify(data, null, 2));
        } else if (tool === "reset-trials") {
          if (!confirm("Сбросить флаг 'free_used' у всех? Они смогут заново активировать пробный.")) return;
          const data = await api("/api/admin/maintenance/reset-all-trials", { method: "POST", body: {} });
          showToast(`Сброшено: ${data.reset}`); log(JSON.stringify(data, null, 2));
        } else if (tool === "clear-payments") {
          if (!confirm("Удалить ВСЮ историю платежей?")) return;
          const data = await api("/api/admin/maintenance/clear-all-payments", { method: "POST", body: {} });
          showToast(`Удалено: ${data.cleared}`); log(JSON.stringify(data, null, 2));
        } else if (tool === "clear-broadcasts") {
          if (!confirm("Удалить ВСЮ историю рассылок?")) return;
          const data = await api("/api/admin/maintenance/clear-broadcasts", { method: "POST", body: {} });
          showToast(`Удалено: ${data.cleared}`); log(JSON.stringify(data, null, 2));
        } else if (tool === "clear-log") {
          if (!confirm("Очистить журнал действий админов?")) return;
          const data = await api("/api/admin/maintenance/clear-log", { method: "POST", body: {} });
          showToast(`Очищено: ${data.cleared}`); log(JSON.stringify(data, null, 2));
        } else if (tool === "reveal-key") {
          const data = await api("/api/internal/key");
          log(`INTERNAL_API_KEY = ${data.key}`);
        } else if (tool === "empty-image-url") {
          const url = ($("emptyImageUrl")?.value || "").trim();
          const data = await api("/api/admin/empty-image/url", { method: "POST", body: { url } });
          showToast("Сохранено");
          const prev = $("emptyImagePreview");
          if (prev) prev.innerHTML = data.url ? `<img src="${data.url}" style="max-height:160px;border-radius:8px"/>` : "—";
        } else if (tool === "empty-image-clear") {
          if (!confirm("Сбросить картинку?")) return;
          const r = await fetch("/api/admin/empty-image", { method: "DELETE", credentials: "include" });
          if (!r.ok) throw new Error("HTTP " + r.status);
          showToast("Сброшено");
          if ($("emptyImageUrl")) $("emptyImageUrl").value = "";
          if ($("emptyImagePreview")) $("emptyImagePreview").innerHTML = "—";
        } else if (
          tool === "zero-balances" || tool === "revoke-subs" ||
          tool === "clear-devices" || tool === "delete-non-admin" || tool === "wipe-all"
        ) {
          const labels = {
            "zero-balances": "Обнулить балансы у ВСЕХ?",
            "revoke-subs": "Снять подписки у ВСЕХ?",
            "clear-devices": "Удалить устройства у ВСЕХ?",
            "delete-non-admin": "Удалить ВСЕХ не-админов?",
            "wipe-all": "Полный wipe — удалить юзеров, платежи, рассылки. Продолжить?",
          };
          const path = {
            "zero-balances": "/api/admin/danger/zero-all-balances",
            "revoke-subs": "/api/admin/danger/revoke-all-subscriptions",
            "clear-devices": "/api/admin/danger/clear-all-devices",
            "delete-non-admin": "/api/admin/danger/delete-all-non-admin",
            "wipe-all": "/api/admin/danger/wipe-all",
          };
          if (!confirm(labels[tool])) return;
          const code = String(Math.floor(10000 + Math.random() * 90000));
          const t = prompt(`Подтверждение: введите код ${code}`, "");
          if ((t || "").trim() !== code) { showToast("Код не совпал"); return; }
          const data = await api(path[tool], { method: "POST", body: { confirm: code } });
          const out2 = $("dangerOutput");
          if (out2) out2.textContent = JSON.stringify(data, null, 2);
          showToast("OK");
        } else if (tool === "unban-all") {
          if (!confirm("Разбанить всех?")) return;
          const data = await api("/api/admin/maintenance/unban-all", { method: "POST", body: {} });
          const out2 = $("dangerOutput");
          if (out2) out2.textContent = JSON.stringify(data, null, 2);
          showToast(`Разбанено: ${data.unbanned}`);
        }
      } catch (error) { showToast(error.message, true); log(error.message); }
    });
  });
  // Maintenance toggles
  document.querySelectorAll("[data-maint]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const action = btn.dataset.maint;
      const message = ($("maintMessage")?.value || "").trim();
      const out = $("maintOutput");
      try {
        let data;
        if (action === "site-on") data = await api("/api/admin/maintenance/site/lock", { method: "POST", body: { locked: true, message } });
        else if (action === "site-off") data = await api("/api/admin/maintenance/site/lock", { method: "POST", body: { locked: false, message: "" } });
        else if (action === "bot-on") data = await api("/api/admin/maintenance/bot/lock", { method: "POST", body: { locked: true, message } });
        else if (action === "bot-off") data = await api("/api/admin/maintenance/bot/lock", { method: "POST", body: { locked: false, message: "" } });
        else if (action === "all-on") data = await api("/api/admin/maintenance/all/lock", { method: "POST", body: { locked: true, message } });
        else if (action === "all-off") data = await api("/api/admin/maintenance/all/lock", { method: "POST", body: { locked: false, message: "" } });
        if (out) out.textContent = JSON.stringify(data, null, 2);
        showToast("OK");
      } catch (error) {
        if (out) out.textContent = error.message;
        showToast(error.message, true);
      }
    });
  });
  // Empty-image upload
  $("emptyImageFile")?.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await fetch("/api/admin/empty-image/upload", {
        method: "POST",
        credentials: "include",
        body: fd,
      });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "HTTP " + r.status);
      showToast(`Загружено · ${Math.round(data.bytes / 1024)} КБ`);
      if ($("emptyImageUrl")) $("emptyImageUrl").value = data.url;
      if ($("emptyImagePreview")) $("emptyImagePreview").innerHTML = `<img src="${data.url}" style="max-height:160px;border-radius:8px"/>`;
    } catch (error) { showToast(error.message, true); }
  });
  $("adminNavToggle")?.addEventListener("click", () => {
    $("adminNav")?.classList.toggle("open");
  });
  $("paymentsTbody").addEventListener("click", async (event) => {
    const approveId = event.target.dataset.payApprove;
    const rejectId = event.target.dataset.payReject;
    if (!approveId && !rejectId) return;
    try {
      if (approveId) await api(`/api/admin/payments/${approveId}/approve`, { method: "POST", body: {} });
      else await api(`/api/admin/payments/${rejectId}/reject`, { method: "POST", body: {} });
      showToast("OK");
      refreshPayments();
    } catch (error) { showToast(error.message, true); }
  });
  $("userDrawer").addEventListener("click", (event) => {
    if (event.target === $("userDrawer")) closeUser();
    const act = event.target.closest("[data-act]");
    if (!act) return;
    const uid = Number($("userDrawer").dataset.uid);
    userAction(uid, act.dataset.act);
  });
  $("tariffEditor").addEventListener("click", (event) => {
    if (event.target.dataset.action === "remove") {
      const row = event.target.closest(".tariff-row");
      const idx = Number(row.dataset.idx);
      state.config.tariffs.splice(idx, 1);
      renderTariffEditor();
    }
  });

  // Analytics handlers
  $("analyticsRefresh")?.addEventListener("click", refreshAnalytics);
  // Events handlers
  $("eventsRefresh")?.addEventListener("click", refreshEvents);
  $("eventsClear")?.addEventListener("click", async () => {
    if (!confirm("Удалить все события?")) return;
    await api("/api/admin/events", { method: "DELETE" });
    refreshEvents();
  });
  // Promo handlers
  $("promosRefresh")?.addEventListener("click", refreshPromos);
  $("promoCreate")?.addEventListener("click", createPromo);
  $("promosTbody")?.addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-promo-act]");
    if (!btn) return;
    const code = btn.dataset.code;
    const act = btn.dataset.promoAct;
    if (act === "delete") {
      if (!confirm(`Удалить промокод ${code}?`)) return;
      await api(`/api/admin/promos/${encodeURIComponent(code)}`, { method: "DELETE" });
    } else if (act === "disable") {
      await api(`/api/admin/promos/${encodeURIComponent(code)}/disable`, { method: "POST", body: {} });
    } else if (act === "copy") {
      try { await navigator.clipboard.writeText(code); showToast("Скопировано"); } catch (e) {}
    }
    refreshPromos();
  });
  // Backup handlers
  $("backupExport")?.addEventListener("click", async () => {
    try {
      const res = await api("/api/admin/backup/export");
      const blob = new Blob([JSON.stringify(res.snapshot, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `jutsovpn-backup-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showToast("Снапшот скачан");
    } catch (e) {
      showToast("Не удалось", true);
    }
  });
  $("backupImportFile")?.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!confirm("Импорт перезапишет текущие данные. Продолжить?")) {
      event.target.value = ""; return;
    }
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const snap = JSON.parse(reader.result);
        const res = await api("/api/admin/backup/import", { method: "POST", body: { snapshot: snap } });
        $("backupOutput").textContent = JSON.stringify(res, null, 2);
        showToast("Импорт завершён");
      } catch (e) {
        $("backupOutput").textContent = String(e);
        showToast("Ошибка импорта", true);
      }
      event.target.value = "";
    };
    reader.readAsText(file);
  });

  setSection("dashboard");
});

// ==== Analytics ====
async function refreshAnalytics() {
  try {
    const [counters, regs, pays, byTariff, top] = await Promise.all([
      api("/api/admin/system/counters").catch(() => ({})),
      api("/api/admin/aggregate/registrations-by-day/14").catch(() => ({})),
      api("/api/admin/aggregate/payments-by-day/14").catch(() => ({})),
      api("/api/admin/aggregate/by-tariff").catch(() => ({})),
      api("/api/admin/users/top-spenders/10").catch(() => ({})),
    ]);
    renderAnalyticsKpis(counters);
    renderBarChart("chartRegistrations", regs.items || regs.days || [], "count");
    renderBarChart("chartPayments", pays.items || pays.days || [], "rub", "₽");
    renderBarChart("chartTariffs", (byTariff.items || []).map((x) => ({ label: x.key || x.name, count: x.count })), "count");
    renderTopSpenders(top.items || []);
  } catch (e) {
    showToast("Ошибка аналитики", true);
  }
}
function renderAnalyticsKpis(counters) {
  const target = $("analyticsKpi");
  if (!target) return;
  const items = [
    { label: "Юзеров", value: counters.users || 0 },
    { label: "Активных подписок", value: counters.active_subs || 0 },
    { label: "Платежей", value: counters.payments || 0 },
    { label: "Сумма ₽", value: fmtRub(counters.total_rub || 0) },
    { label: "Stars ⭐", value: counters.total_stars || 0 },
    { label: "Сегодня регистраций", value: counters.today_registrations || 0 },
  ];
  target.innerHTML = items.map((x) => `<div class="kpi-card"><div class="kpi-label">${escapeHtml(String(x.label))}</div><div class="kpi-value">${escapeHtml(String(x.value))}</div></div>`).join("");
}
function renderBarChart(id, rows, key, suffix) {
  const target = $(id);
  if (!target) return;
  if (!rows.length) { target.innerHTML = '<div class="admin-hint">Нет данных</div>'; return; }
  const max = Math.max(...rows.map((r) => Number(r[key]) || 0)) || 1;
  target.innerHTML = rows.map((r) => {
    const v = Number(r[key]) || 0;
    const pct = Math.round((v / max) * 100);
    const lbl = r.label || r.day || r.date || "";
    return `<div class="bar-row"><div class="bar-label">${escapeHtml(String(lbl))}</div><div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div><div class="bar-value">${escapeHtml(String(v))}${suffix ? " " + suffix : ""}</div></div>`;
  }).join("");
}
function renderTopSpenders(items) {
  const target = $("topSpendersTbody");
  if (!target) return;
  if (!items.length) { target.innerHTML = '<tr><td colspan="4" class="admin-hint">Нет платящих пользователей</td></tr>'; return; }
  target.innerHTML = items.map((x, i) => `<tr><td>${i + 1}</td><td>${escapeHtml(x.first_name || "—")} <span class="dim">${x.id}</span></td><td>${fmtRub(x.spent_rub || 0)}</td><td>${x.payments_count || 0}</td></tr>`).join("");
}

// ==== Events ====
async function refreshEvents() {
  const tg = ($("eventsTgId")?.value || "").trim();
  const type = ($("eventsType")?.value || "").trim();
  const params = new URLSearchParams();
  if (tg) params.set("tg_id", tg);
  if (type) params.set("type", type);
  params.set("limit", "200");
  const target = $("eventsTbody");
  try {
    const res = await api(`/api/admin/events?${params.toString()}`);
    const items = res.items || [];
    $("eventsMeta").textContent = `Всего: ${res.total ?? items.length}`;
    if (!items.length) { target.innerHTML = '<tr><td colspan="5" class="admin-hint">Пока пусто</td></tr>'; return; }
    target.innerHTML = items.map((e) => `<tr><td>${fmtTs(e.ts)}</td><td>${e.tg_id || "—"}</td><td><code>${escapeHtml(e.type || "")}</code></td><td>${escapeHtml(e.label || "")}</td><td class="dim">${escapeHtml(e.source || "")}</td></tr>`).join("");
  } catch (e) {
    target.innerHTML = '<tr><td colspan="5" class="admin-hint">Не удалось загрузить</td></tr>';
  }
}

// ==== Promo codes ====
async function refreshPromos() {
  const target = $("promosTbody");
  try {
    const res = await api("/api/admin/promos");
    const items = res.items || [];
    if (!items.length) { target.innerHTML = '<tr><td colspan="8" class="admin-hint">Промокодов нет</td></tr>'; return; }
    target.innerHTML = items.map((p) => {
      const exp = p.expires_at ? new Date(p.expires_at * 1000).toLocaleDateString("ru-RU") : "∞";
      const lim = p.limit ? p.limit : "∞";
      return `<tr>
        <td><code>${escapeHtml(p.code)}</code></td>
        <td>${escapeHtml(p.kind)}</td>
        <td>${p.value}</td>
        <td>${p.used || 0}</td>
        <td>${lim}</td>
        <td>${exp}</td>
        <td class="dim">${escapeHtml(p.note || "")}</td>
        <td>
          <button class="admin-btn small ghost" data-promo-act="copy" data-code="${escapeHtml(p.code)}">Копировать</button>
          <button class="admin-btn small warn" data-promo-act="disable" data-code="${escapeHtml(p.code)}">Отключить</button>
          <button class="admin-btn small danger" data-promo-act="delete" data-code="${escapeHtml(p.code)}">×</button>
        </td>
      </tr>`;
    }).join("");
  } catch (e) {
    target.innerHTML = '<tr><td colspan="8" class="admin-hint">Не удалось загрузить</td></tr>';
  }
}
async function createPromo() {
  const body = {
    code: ($("promoCode")?.value || "").trim().toUpperCase(),
    kind: $("promoKind")?.value || "balance",
    value: Number($("promoValue")?.value || 0),
    limit: Number($("promoLimit")?.value || 0),
    expires_in_days: Number($("promoExpires")?.value || 0),
    note: ($("promoNote")?.value || "").trim(),
  };
  if (!body.value || body.value <= 0) { showToast("Укажите положительное значение", true); return; }
  try {
    const res = await api("/api/admin/promos", { method: "POST", body });
    showToast(`Создан: ${res.code}`);
    $("promoCode").value = "";
    $("promoNote").value = "";
    refreshPromos();
  } catch (e) {
    showToast(e.message || "Ошибка", true);
  }
}
