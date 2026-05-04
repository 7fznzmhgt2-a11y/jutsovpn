const MAX_ACCOUNT_DEVICES = 10;
const PAYMENT_TTL_MS = 15 * 60 * 1000;
const LIVE_REFRESH_MS = 3000;
const LIVE_REFRESH_PENDING_MS = 1500;
const LIVE_PAYMENT_CHECK_MS = 5000;
const LIVE_FAST_WINDOW_MS = 90 * 1000;
const IS_BROWSER_CABINET = location.pathname.replace(/\/+$/, "") === "/cabinet";
const BATTERY_EMOJI_PATHS = [
  "/static/emoji_battery_4.json",
  "/static/emoji_battery_3.json",
  "/static/emoji_battery_2.json",
  "/static/emoji_battery_1.json",
];
const COLLAPSE_EMOJI_PATH = "/static/emoji_542718194293_white.json?v=20260419menu2";
const DEVICE_EMPTY_GIRL_PATH = "/static/emoji_628078191105.json?v=20260419device1";
const SUCCESS_EMOJI_PATH = "/static/emoji_628078117231.json?v=20260420success1";
const TOUR_STEPS = [
  { tab: "home",    titleKey: "home_title",    textKey: "tour_home_text" },
  { tab: "buy",     titleKey: "buy_title",     textKey: "tour_buy_text" },
  { tab: "finance", titleKey: "finance_title", textKey: "tour_finance_text" },
  { tab: "profile", titleKey: "profile_title", textKey: "tour_profile_text" },
];

const state = {
  config: null,
  session: null,
  dashboard: null,
  pendingDeviceDelete: null,
  activeTab: "home",
  expandedPurchase: null,
  purchaseProvider: "",
  purchaseCollapseOpen: false,
  balanceCollapseOpen: false,
  purchaseCheckVisible: false,
  balanceCheckVisible: false,
  purchaseStartedAt: 0,
  purchaseStatus: "",
  loadingProgress: 0,
  loadingProgressTimer: null,
  countdownTimer: null,
  liveRefreshTimer: null,
  liveRefreshInFlight: false,
  liveRefreshLastSignature: "",
  liveRefreshFastUntil: 0,
  liveRefreshLastPaymentCheck: 0,
  liveRefreshLastConfigCheck: 0,
  liveRefreshErrorCount: 0,
  prefersReducedMotion: false,
  deviceEmptyGirlObserver: null,
  deviceEmptyGirlPlayed: false,
  trialStep: "intro",
  tourActive: false,
  tourStep: 0,
  successModalVisible: false,
  animations: {},
  giftTariffKey: "",
  giftDeviceCount: 1,
  giftProvider: "",
  giftCheckVisible: false,
  giftRecipientCandidate: null,
  giftRecipientSelected: null,
  giftRecipientStatus: "idle",
  giftRecipientTimer: null,
  giftRecipientSeq: 0,
  giftRecipientCache: {},
  pushSupported: false,
  pushSubscribed: false,
  pushPromptShown: false,
  unreadNotifications: [],
  settingsOpen: false,
};

const deviceIconsWhite = {
  windows: '<svg class="platform-logo" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5.4 10.8 4.3v7.4H3V5.4Zm9.2-1.3L21 2.8v8.9h-8.8V4.1ZM3 12.9h7.8v7.2L3 19v-6.1Zm9.2 0H21v8.3l-8.8-1.2v-7.1Z"/></svg>',
  android: '<svg class="platform-logo" viewBox="0 0 24 24" aria-hidden="true"><path d="M7.5 9.2h9A2.5 2.5 0 0 1 19 11.7v4.9a3.4 3.4 0 0 1-3.4 3.4H8.4A3.4 3.4 0 0 1 5 16.6v-4.9a2.5 2.5 0 0 1 2.5-2.5Zm-.1-1.5c.5-1 1.3-1.8 2.3-2.3L8.8 3.7a.7.7 0 0 1 1.2-.7l1 1.9a7 7 0 0 1 2 0l1-1.9a.7.7 0 1 1 1.2.7l-.9 1.7c1 .5 1.8 1.3 2.3 2.3H7.4Zm2.2 5.2a.85.85 0 1 0 0-1.7.85.85 0 0 0 0 1.7Zm4.8 0a.85.85 0 1 0 0-1.7.85.85 0 0 0 0 1.7Z"/></svg>',
  ios: '<svg class="platform-logo" viewBox="0 0 24 24" aria-hidden="true"><path d="M16.2 12.4c0-2 1.7-3 1.8-3.1-1-1.4-2.5-1.6-3-1.6-1.3-.1-2.5.8-3.1.8-.7 0-1.7-.8-2.8-.7-1.4 0-2.7.8-3.4 2.1-1.5 2.6-.4 6.4 1 8.5.7 1 1.6 2.2 2.7 2.1 1.1 0 1.5-.7 2.8-.7s1.7.7 2.9.7 1.9-1 2.6-2.1c.8-1.2 1.2-2.4 1.2-2.5 0 0-2.6-1-2.7-3.5ZM14.2 6.3c.6-.7 1-1.7.9-2.7-.9 0-1.9.6-2.6 1.3-.6.6-1.1 1.7-.9 2.6.9.1 2-.5 2.6-1.2Z"/></svg>',
  macos: '<svg class="platform-logo" viewBox="0 0 24 24" aria-hidden="true"><path d="M16.2 12.4c0-2 1.7-3 1.8-3.1-1-1.4-2.5-1.6-3-1.6-1.3-.1-2.5.8-3.1.8-.7 0-1.7-.8-2.8-.7-1.4 0-2.7.8-3.4 2.1-1.5 2.6-.4 6.4 1 8.5.7 1 1.6 2.2 2.7 2.1 1.1 0 1.5-.7 2.8-.7s1.7.7 2.9.7 1.9-1 2.6-2.1c.8-1.2 1.2-2.4 1.2-2.5 0 0-2.6-1-2.7-3.5ZM14.2 6.3c.6-.7 1-1.7.9-2.7-.9 0-1.9.6-2.6 1.3-.6.6-1.1 1.7-.9 2.6.9.1 2-.5 2.6-1.2Z"/></svg>',
  linux: '<svg class="platform-logo" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.4c2.1 0 3.6 1.7 3.6 4.2v1.5c0 1 .4 1.8 1.1 2.6 1.2 1.2 2.1 3 2.1 5.2 0 3.3-2.8 5.7-6.8 5.7s-6.8-2.4-6.8-5.7c0-2.2.9-4 2.1-5.2.7-.8 1.1-1.6 1.1-2.6V6.6c0-2.5 1.5-4.2 3.6-4.2Zm-2.7 12c-1 1-1.6 2.1-1.6 3.2 0 1.5 1.2 2.4 3.1 2.8-.9-1.1-1.4-2.7-1.5-4.5v-1.5Zm5.4 0v1.5c-.1 1.8-.6 3.4-1.5 4.5 1.9-.4 3.1-1.3 3.1-2.8 0-1.1-.6-2.2-1.6-3.2ZM10 7.2a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8Zm4 0a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8Zm-2 1.5c-.8 0-1.5.5-1.5 1.1s.7 1.1 1.5 1.1 1.5-.5 1.5-1.1-.7-1.1-1.5-1.1Z"/></svg>',
  default: '<svg class="platform-logo platform-logo-default" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-5v2h3a1 1 0 1 1 0 2H7a1 1 0 1 1 0-2h3v-2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Zm0 2v8h14V7H5Z"/></svg>',
};

const ERROR_MESSAGES = {
  promo_not_found: "Промокод не найден",
  promo_unavailable: "Промокод недоступен или уже использован",
  promo_empty: "Этот промокод ничего не начисляет",
  invalid_code: "Некорректный промокод",
  free_already_used: "Пробный период уже был использован",
  channel_required: "Подпишитесь на канал и попробуйте снова",
  insufficient_balance: "Недостаточно средств на балансе",
  invalid_amount: "Некорректная сумма",
  invalid_count: "Некорректное количество",
  invalid_tariff: "Неверный тариф",
  subscription_required: "Сначала оформите подписку",
  payment_unavailable: "Способ оплаты временно недоступен",
  gift_recipient_not_found: "Получатель не найден в локальной базе",
  gift_not_found: "Подарок не найден",
  gift_not_ready: "Подарок ещё не оплачен",
  gift_already_claimed: "Подарок уже получен",
  gift_wrong_recipient: "Этот подарок предназначен другому аккаунту",
  auth_required: "Нужна авторизация",
  telegram_validation_failed: "Ошибка входа через Telegram",
  telegram_webapp_validation_failed: "Ошибка авторизации Web App",
};

const SUCCESS_MESSAGES = {
  promo_activated: "Промокод активирован",
  promo_applied: "Промокод успешно применен",
  payment_created: "Платеж создан",
  payment_success: "Оплата прошла успешно",
  subscription_activated: "Подписка активирована",
  free_trial_activated: "Пробный период активирован",
  copied: "Ссылка скопирована",
};

const $ = (id) => document.getElementById(id);

function isTelegramWebApp() {
  return Boolean(window.Telegram?.WebApp?.initData);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function localizeMessage(message) {
  const raw = String(message || "").trim();
  if (!raw) return "Произошла ошибка";
  if (ERROR_MESSAGES[raw]) return ERROR_MESSAGES[raw];
  if (SUCCESS_MESSAGES[raw]) return SUCCESS_MESSAGES[raw];
  return raw;
}

// Lightweight telemetry: queues events and flushes them in batches so we never
// block UI. Survives auth-failure (401) silently.
const _eventQueue = [];
let _eventFlushTimer = null;
function logEvent(type, label, payload) {
  try {
    _eventQueue.push({
      type: String(type || "unknown").slice(0, 48),
      label: label != null ? String(label).slice(0, 160) : null,
      payload: payload && typeof payload === "object" ? payload : undefined,
      source: "frontend",
    });
    if (!_eventFlushTimer) {
      _eventFlushTimer = setTimeout(flushEvents, 1500);
    }
  } catch {}
}
async function flushEvents() {
  _eventFlushTimer = null;
  if (!_eventQueue.length) return;
  const batch = _eventQueue.splice(0, _eventQueue.length);
  try {
    await fetch("/api/log/event", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: batch }),
    });
  } catch {}
}
window.addEventListener("beforeunload", () => {
  try {
    if (_eventQueue.length && navigator.sendBeacon) {
      navigator.sendBeacon(
        "/api/log/event",
        new Blob([JSON.stringify({ events: _eventQueue.splice(0, _eventQueue.length) })], { type: "application/json" }),
      );
    }
  } catch {}
});

async function request(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {
      "Content-Type": "application/json",
      "ngrok-skip-browser-warning": "true",
      ...(options.headers || {}),
    },
  });

  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    throw new Error("Сервер вернул страницу вместо данных. Откройте мини-апп заново.");
  }

  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }

  return data;
}

function urlBase64ToUint8Array(value) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  return Uint8Array.from([...raw].map((char) => char.charCodeAt(0)));
}

function pushStorageKey() {
  const tgId = state.session?.tg_id || state.dashboard?.profile?.tg_id || "guest";
  return `sendvpn:push-prompt:${tgId}`;
}

function settingsStorageKey(name) {
  const tgId = state.session?.tg_id || state.dashboard?.profile?.tg_id || "guest";
  return `sendvpn:settings:${name}:${tgId}`;
}

function readLocalSetting(name, fallback) {
  try {
    const raw = window.localStorage?.getItem(settingsStorageKey(name));
    if (raw === null || raw === undefined) return fallback;
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function writeLocalSetting(name, value) {
  try {
    window.localStorage?.setItem(settingsStorageKey(name), JSON.stringify(value));
  } catch {
    // ignore storage restrictions
  }
}

function isPushAvailable() {
  if (isTelegramWebApp()) return false;
  return Boolean(
    window.isSecureContext &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

function updatePushButton() {
  const button = $("pushPermissionButton");
  if (!button) return;
  state.pushSupported = isPushAvailable();
  if (!state.pushSupported) {
    button.textContent = "Уведомления недоступны";
    button.disabled = true;
    return;
  }
  if (Notification.permission === "denied") {
    button.textContent = "Уведомления запрещены";
    button.disabled = true;
    return;
  }
  button.disabled = false;
  button.textContent = state.pushSubscribed || Notification.permission === "granted"
    ? "Уведомления включены"
    : "Разрешить уведомления";
}

function hidePushPrompt() {
  $("pushSheet")?.classList.add("hidden");
}

function syncBotWebAppChrome() {
  const inBot = isTelegramWebApp();
  document.body.classList.toggle("bot-webapp", inBot);
  ["pushPermissionButton", "logoutButton"].forEach((id) => {
    $(id)?.classList.toggle("hidden", inBot);
  });
  if (inBot) {
    hidePushPrompt();
    hideNotificationSheet();
  }
}

function showNotificationSheet(notifications = state.unreadNotifications) {
  if (isTelegramWebApp()) return;
  const sheet = $("notificationSheet");
  const list = $("notificationList");
  if (!sheet || !list) return;
  const items = Array.isArray(notifications) ? notifications : [];
  state.unreadNotifications = items;
  if (!items.length) {
    sheet.classList.add("hidden");
    return;
  }
  $("notificationTitle").textContent = `У вас ${items.length} непрочит.`;
  list.innerHTML = items.map((item) => `
    <article class="notification-item">
      <div class="notification-icon" aria-hidden="true">
        <img src="/static/sendvpn-icon-192.png" alt="">
      </div>
      <div class="notification-copy">
        <strong>${escapeHtml(item.title || "JutsoVPN")}</strong>
        <p>${escapeHtml(item.message || "")}</p>
      </div>
      <button class="cta cta-primary cta-small notification-action" type="button" data-notification="${escapeHtml(item.id)}">
        ${item.kind === "gift" ? "Получить" : "Открыть"}
      </button>
    </article>
  `).join("");
  list.querySelectorAll(".notification-action").forEach((button) => {
    button.addEventListener("click", () => handleNotificationAction(button.dataset.notification));
  });
  sheet.classList.remove("hidden");
}

function hideNotificationSheet() {
  $("notificationSheet")?.classList.add("hidden");
}

async function markNotificationsRead(ids = null) {
  try {
    await request("/api/notifications/read", {
      method: "POST",
      body: JSON.stringify(ids ? { ids } : {}),
    });
  } catch {
    // best effort
  }
}

async function handleNotificationAction(id) {
  const item = state.unreadNotifications.find((entry) => String(entry.id) === String(id));
  if (!item) return;
  const actionUrl = String(item.action_url || "/cabinet");
  const giftMatch = actionUrl.match(/[?&]gift=([^&]+)/);
  if (giftMatch) {
    await claimGift(decodeURIComponent(giftMatch[1]), Number(item.id));
    return;
  }
  await markNotificationsRead([Number(item.id)]);
  state.unreadNotifications = state.unreadNotifications.filter((entry) => String(entry.id) !== String(item.id));
  if (!state.unreadNotifications.length) hideNotificationSheet();
  else showNotificationSheet();
  if (actionUrl && actionUrl !== "/cabinet") window.location.href = actionUrl;
}

async function dismissNotifications() {
  const ids = state.unreadNotifications.map((item) => Number(item.id)).filter(Boolean);
  await markNotificationsRead(ids);
  state.unreadNotifications = [];
  hideNotificationSheet();
}

async function claimGift(code, notificationId = null) {
  if (!code) return;
  try {
    const result = await request(`/api/gifts/${encodeURIComponent(code)}/claim`, {
      method: "POST",
      body: "{}",
    });
    if (notificationId) {
      state.unreadNotifications = state.unreadNotifications.filter((item) => Number(item.id) !== Number(notificationId));
    }
    if (!state.unreadNotifications.length) hideNotificationSheet();
    else showNotificationSheet();
    applyDashboardUpdate(result.dashboard, state.session, { force: true });
    showSuccessModal("Подарок получен", result.detail || result.message || "Подарок активирован.");
    showToast(result.message || "Подарок активирован");
  } catch (error) {
    showToast(error.message || "Не удалось получить подарок");
  }
}

async function claimGiftFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("gift");
  if (!code || !state.session) return;
  params.delete("gift");
  const nextQuery = params.toString();
  const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ""}${window.location.hash}`;
  window.history.replaceState({}, "", nextUrl);
  await claimGift(code);
}

function maybeShowPushPrompt() {
  updatePushButton();
  if (!state.session || !state.pushSupported || state.pushSubscribed) return;
  if (Notification.permission !== "default") return;
  try {
    if (window.localStorage?.getItem(pushStorageKey()) === "done") return;
  } catch {
    return;
  }
  if (state.pushPromptShown) return;
  state.pushPromptShown = true;
  $("pushSheet")?.classList.remove("hidden");
}

async function enablePushNotifications() {
  if (!isPushAvailable()) {
    showToast("Откройте сайт как приложение с экрана Домой");
    updatePushButton();
    return;
  }
  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      showToast(permission === "denied" ? "Уведомления запрещены в настройках" : "Уведомления не включены");
      updatePushButton();
      return;
    }

    const registration = await navigator.serviceWorker.register("/sw.js");
    const existing = await registration.pushManager.getSubscription();
    const subscription = existing || await (async () => {
      const keyData = await request("/api/push/public-key");
      const publicKey = String(keyData.public_key || "");
      if (!publicKey) throw new Error("Ключ уведомлений недоступен");
      return registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
    })();

    await request("/api/push/subscribe", {
      method: "POST",
      body: JSON.stringify({ subscription: subscription.toJSON() }),
    });
    state.pushSubscribed = true;
    hidePushPrompt();
    try {
      window.localStorage?.setItem(pushStorageKey(), "done");
    } catch {
      // ignore storage restrictions
    }
    updatePushButton();
    showSuccessModal("Уведомления включены", "Теперь сайт сможет присылать важные события по подписке и подаркам.");
  } catch (error) {
    showToast(error.message || "Не удалось включить уведомления");
    updatePushButton();
  }
}

async function refreshPushState() {
  state.pushSupported = isPushAvailable();
  state.pushSubscribed = false;
  if (!state.pushSupported || Notification.permission !== "granted") {
    updatePushButton();
    return;
  }
  try {
    const registration = await navigator.serviceWorker.register("/sw.js");
    const subscription = await registration.pushManager.getSubscription();
    state.pushSubscribed = Boolean(subscription);
  } catch {
    state.pushSubscribed = false;
  }
  updatePushButton();
}

async function logout() {
  try {
    if (isPushAvailable()) {
      const registration = await navigator.serviceWorker.getRegistration("/");
      const subscription = await registration?.pushManager?.getSubscription?.();
      if (subscription) {
        await request("/api/push/unsubscribe", {
          method: "POST",
          body: JSON.stringify({ endpoint: subscription.endpoint }),
        }).catch(() => {});
      }
    }
    await request("/api/logout", { method: "POST", body: "{}" });
    state.session = null;
    state.dashboard = null;
    state.pushSubscribed = false;
    clearCachedDashboard();
    hidePushPrompt();
    setBrowserAuthGate(true);
    installTelegramLoginWidget();
    switchTab("home");
    showToast("Вы вышли из аккаунта");
  } catch (error) {
    showToast(error.message || "Не удалось выйти");
  }
}

function showToast(message) {
  const toast = $("toast");
  if (!toast) return;
  toast.textContent = localizeMessage(message);
  toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add("hidden"), 2600);
}

function showSuccessModal(title, text) {
  const overlay = $("successOverlay");
  if (!overlay) return;
  $("successTitle").textContent = title || "Готово";
  $("successText").textContent = text || "Операция выполнена успешно.";
  overlay.classList.remove("hidden");
  state.successModalVisible = true;
  ensureLottieAnimation("successModal", "successEmoji", SUCCESS_EMOJI_PATH, {
    renderer: "svg",
    loop: true,
    autoplay: true,
    speed: state.prefersReducedMotion ? 0.75 : 0.95,
  });
}

function hideSuccessModal() {
  const overlay = $("successOverlay");
  if (!overlay) return;
  overlay.classList.add("hidden");
  state.successModalVisible = false;
  state.animations.successModal?.destroy?.();
  delete state.animations.successModal;
}

function renderReferralSheet() {
  const referrals = state.dashboard?.referrals || {};
  const days = Number(referrals.trial_bonus_days || 4);
  const percent = Number(referrals.purchase_percent || 20);
  const link = String(referrals.link || "").trim();

  if ($("referralTotalValue")) $("referralTotalValue").textContent = String(referrals.total || 0);
  if ($("referralActiveValue")) $("referralActiveValue").textContent = String(referrals.active || 0);
  if ($("referralBonusValue")) $("referralBonusValue").textContent = formatRub(referrals.bonus_total || 0);
  if ($("referralTrialRule")) $("referralTrialRule").textContent = t("ref_trial_rule", { n: days });
  if ($("referralPurchaseRule")) $("referralPurchaseRule").textContent = t("ref_purchase_rule", { n: percent });
  if ($("referralLinkValue")) $("referralLinkValue").textContent = link || "Ссылка пока недоступна";
}

function showReferralSheet() {
  renderReferralSheet();
  $("referralSheet")?.classList.remove("hidden");
}

function hideReferralSheet() {
  $("referralSheet")?.classList.add("hidden");
}

function getGiftTariff() {
  return getTariffByKey(state.giftTariffKey);
}

function giftAmount() {
  if (state.giftTariffKey === "devices") {
    return Number(state.config?.extra_device_rub || 0) * Number(state.giftDeviceCount || 1);
  }
  return Number(getGiftTariff()?.rub || 0);
}

function ensureGiftProvider() {
  const providers = providerOptions(true, giftAmount());
  if (!providers.includes(state.giftProvider)) state.giftProvider = "";
  return state.giftProvider;
}

function updateGiftPayButtonState() {
  const payButton = $("giftPayButton");
  const lookupPending = state.giftRecipientStatus === "searching" || state.giftRecipientStatus === "typing";
  if (payButton) payButton.disabled = !state.giftProvider || lookupPending;
}

function resetGiftRecipient({ clearInput = false } = {}) {
  clearTimeout(state.giftRecipientTimer);
  state.giftRecipientCandidate = null;
  state.giftRecipientSelected = null;
  state.giftRecipientStatus = "idle";
  state.giftRecipientSeq += 1;
  if (clearInput && $("giftRecipientInput")) $("giftRecipientInput").value = "";
  renderGiftRecipientLookup();
  updateGiftPayButtonState();
}

function giftRecipientTitle(recipient) {
  const name = String(recipient?.name || "").trim();
  const username = String(recipient?.username || "").trim();
  if (name && !/^\d+$/.test(name)) return name;
  if (username) return `@${username}`;
  return `Telegram ID ${recipient?.tg_id || ""}`;
}

function giftRecipientMeta(recipient) {
  const username = String(recipient?.username || "").trim();
  const id = String(recipient?.tg_id || "").trim();
  return username ? `@${username} · ID ${id}` : `ID ${id}`;
}

function giftRecipientInitial(recipient) {
  const title = giftRecipientTitle(recipient).replace(/^@/, "").trim();
  return (title[0] || "S").toUpperCase();
}

function renderGiftRecipientLookup() {
  const panel = $("giftRecipientLookup");
  if (!panel) return;
  const raw = String($("giftRecipientInput")?.value || "").trim();
  const candidate = state.giftRecipientCandidate;
  const selected = state.giftRecipientSelected;

  if (!raw && !candidate && !selected && state.giftRecipientStatus !== "searching") {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }

  panel.classList.remove("hidden");
  if (state.giftRecipientStatus === "searching") {
    panel.innerHTML = `<div class="gift-recipient-note">Ищем пользователя в базе...</div>`;
    return;
  }

  if (state.giftRecipientStatus === "not_found") {
    panel.innerHTML = `
      <div class="gift-recipient-empty">
        <strong>Пользователя нет в базе</strong>
        <span>Попросите друга открыть бота хотя бы один раз. Либо оплатите без получателя: после оплаты появится ссылка для активации подарка.</span>
      </div>
      <button class="gift-link-mode-button" id="giftLinkModeButton" type="button">Получить ссылку после оплаты</button>
    `;
    $("giftLinkModeButton")?.addEventListener("click", () => resetGiftRecipient({ clearInput: true }));
    return;
  }

  if (state.giftRecipientStatus === "error") {
    panel.innerHTML = `<div class="gift-recipient-note">Не получилось проверить получателя. Можно очистить поле и оплатить подарком-ссылкой.</div>`;
    return;
  }

  const user = selected || candidate;
  if (!user) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }

  const isSelected = Boolean(selected);
  const avatar = user.avatar_url
    ? `<img src="${escapeHtml(user.avatar_url)}" alt="">`
    : `<span>${escapeHtml(giftRecipientInitial(user))}</span>`;
  panel.innerHTML = `
    <div class="gift-recipient-card ${isSelected ? "is-selected" : ""}">
      <div class="gift-recipient-avatar">${avatar}</div>
      <div class="gift-recipient-info">
        <strong>${escapeHtml(giftRecipientTitle(user))}</strong>
        <span>${escapeHtml(giftRecipientMeta(user))}</span>
      </div>
      <div class="gift-recipient-actions">
        <button class="gift-recipient-pick" id="giftRecipientPickButton" type="button">${isSelected ? "Выбран" : "Выбрать"}</button>
        ${isSelected ? `<button class="gift-recipient-clear" id="giftRecipientClearButton" type="button" aria-label="Убрать получателя">×</button>` : ""}
      </div>
    </div>
    ${isSelected
      ? `<div class="gift-recipient-note">Подарок придёт этому пользователю в бот.</div>`
      : `<div class="gift-recipient-note">${user.hydrated ? "Нажмите «Выбрать», чтобы закрепить получателя за подарком." : "Подтягиваем настоящее имя и фото..."}</div>`}
  `;
  const selectRecipient = () => {
    state.giftRecipientSelected = { ...user };
    state.giftRecipientStatus = "selected";
    renderGiftRecipientLookup();
    updateGiftPayButtonState();
  };
  if (!isSelected) panel.querySelector(".gift-recipient-card")?.addEventListener("click", selectRecipient);
  $("giftRecipientPickButton")?.addEventListener("click", (event) => {
    event.stopPropagation();
    selectRecipient();
  });
  $("giftRecipientClearButton")?.addEventListener("click", () => resetGiftRecipient({ clearInput: true }));
}

async function lookupGiftRecipientNow() {
  const raw = String($("giftRecipientInput")?.value || "").trim();
  if (!raw) {
    resetGiftRecipient();
    return;
  }
  const cacheKey = raw.toLowerCase();
  if (state.giftRecipientCache[cacheKey]) {
    const cached = state.giftRecipientCache[cacheKey];
    state.giftRecipientCandidate = cached.found ? cached.recipient : null;
    state.giftRecipientSelected = null;
    state.giftRecipientStatus = cached.found ? "found" : "not_found";
    renderGiftRecipientLookup();
    updateGiftPayButtonState();
    if (cached.found && cached.recipient && !cached.recipient.hydrated) {
      hydrateGiftRecipientDetails(cacheKey, raw, cached.recipient.tg_id);
    }
    return;
  }
  const seq = state.giftRecipientSeq + 1;
  state.giftRecipientSeq = seq;
  state.giftRecipientCandidate = null;
  state.giftRecipientSelected = null;
  state.giftRecipientStatus = "searching";
  renderGiftRecipientLookup();
  updateGiftPayButtonState();
  try {
    const result = await request("/api/gifts/recipient", {
      method: "POST",
      body: JSON.stringify({ recipient: raw }),
    });
    if (seq !== state.giftRecipientSeq) return;
    if (result.found && result.recipient) {
      state.giftRecipientCache[cacheKey] = { found: true, recipient: result.recipient };
      state.giftRecipientCandidate = result.recipient;
      state.giftRecipientStatus = "found";
      hydrateGiftRecipientDetails(cacheKey, raw, result.recipient.tg_id);
    } else {
      state.giftRecipientCache[cacheKey] = { found: false };
      state.giftRecipientCandidate = null;
      state.giftRecipientStatus = "not_found";
    }
  } catch {
    if (seq !== state.giftRecipientSeq) return;
    state.giftRecipientCandidate = null;
    state.giftRecipientStatus = "error";
  }
  renderGiftRecipientLookup();
  updateGiftPayButtonState();
}

async function hydrateGiftRecipientDetails(cacheKey, raw, tgId) {
  const cached = state.giftRecipientCache[cacheKey];
  if (!cached?.found || cached.loadingDetails || cached.recipient?.hydrated) return;
  cached.loadingDetails = true;
  try {
    const result = await request("/api/gifts/recipient", {
      method: "POST",
      body: JSON.stringify({ recipient: raw, details: true }),
    });
    if (!result.found || !result.recipient || Number(result.recipient.tg_id) !== Number(tgId)) return;
    const updated = { ...cached.recipient, ...result.recipient, hydrated: true };
    state.giftRecipientCache[cacheKey] = { found: true, recipient: updated };
    if (Number(state.giftRecipientCandidate?.tg_id || 0) === Number(tgId)) {
      state.giftRecipientCandidate = updated;
    }
    if (Number(state.giftRecipientSelected?.tg_id || 0) === Number(tgId)) {
      state.giftRecipientSelected = updated;
    }
    renderGiftRecipientLookup();
  } catch {
    cached.loadingDetails = false;
  }
}

function scheduleGiftRecipientLookup() {
  clearTimeout(state.giftRecipientTimer);
  state.giftRecipientSelected = null;
  state.giftRecipientCandidate = null;
  const raw = String($("giftRecipientInput")?.value || "").trim();
  if (!raw) {
    resetGiftRecipient();
    return;
  }
  state.giftRecipientStatus = "typing";
  renderGiftRecipientLookup();
  updateGiftPayButtonState();
  state.giftRecipientTimer = setTimeout(lookupGiftRecipientNow, 180);
}

function renderGiftSheet() {
  const isDevices = state.giftTariffKey === "devices";
  const tariff = getGiftTariff();
  if (!isDevices && !tariff) return;
  const amount = giftAmount();
  const providers = providerOptions(true, amount);
  const selected = ensureGiftProvider();
  const count = Math.min(Math.max(Number(state.giftDeviceCount || 1), 1), 7);
  if ($("giftTitle")) $("giftTitle").textContent = isDevices ? "Подарить устройства" : "Подарить доступ";
  if ($("giftLead")) {
    $("giftLead").textContent = isDevices
      ? "Выберите количество устройств и получателя. Друг активирует подарок на своей подписке."
      : "Выберите получателя или оставьте поле пустым, чтобы получить ссылку.";
  }
  $("giftSummary").innerHTML = `
    <span class="gift-summary-label">Выбранный подарок</span>
    <strong>${isDevices ? "Дополнительные устройства" : escapeHtml(tariff.name)}</strong>
    <span>${isDevices ? `+${count} устройств к подписке` : `${Number(tariff.days || 0)} дней / ${Number(tariff.devices || 0)} устройства`}</span>
    <b>${formatRub(amount)}</b>
  `;
  const deviceChooser = $("giftDeviceChooser");
  if (deviceChooser) {
    deviceChooser.classList.toggle("hidden", !isDevices);
    const output = $("giftDeviceCountOutput");
    const allowance = $("giftDeviceAllowance");
    const range = $("giftDeviceRange");
    if (output) output.textContent = String(count);
    if (allowance) allowance.textContent = `${count} × ${formatRub(Number(state.config?.extra_device_rub || 0))}`;
    if (range) range.value = String(count);
  }
  const giftStatus = $("giftStatus");
  if (giftStatus && !state.giftCheckVisible) {
    giftStatus.textContent = isDevices
      ? "Получателю нужна активная подписка. После активации лимит не сможет быть больше 10 устройств."
      : "После оплаты другу придёт уведомление или ссылка для активации.";
  }
  const list = $("giftProviderList");
  if (list) {
    list.innerHTML = providers.length
      ? providers.map((provider) => `
          <button class="payment-method gift-provider-button ${provider === selected ? "is-selected" : ""}" type="button" data-provider="${provider}">
            <span class="payment-method-label">${getProviderLabel(provider)}</span>
            <strong class="payment-method-meta">${provider === selected ? "Выбран" : "Выбрать"}</strong>
          </button>
        `).join("")
      : `<div class="purchase-status">Нет доступных способов оплаты</div>`;
  }
  updateGiftPayButtonState();
  $("giftCheckPaymentsButton")?.classList.toggle("hidden", !state.giftCheckVisible);
  renderGiftRecipientLookup();

  document.querySelectorAll(".gift-provider-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.giftProvider = button.dataset.provider || "";
      updatePaymentMethodLabels(document.querySelectorAll(".gift-provider-button"), button);
      updateGiftPayButtonState();
      const status = $("giftStatus");
      if (status) status.textContent = "Способ оплаты выбран. Можно оплачивать подарок.";
    });
  });
}

function showGiftSheet(tariffKey, deviceCount = 1) {
  state.giftTariffKey = tariffKey;
  state.giftDeviceCount = Math.min(Math.max(Number(deviceCount || 1), 1), 7);
  state.giftProvider = "";
  state.giftCheckVisible = false;
  $("giftRecipientInput").value = "";
  $("giftMessageInput").value = "";
  $("giftShowSenderInput").checked = true;
  resetGiftRecipient();
  $("giftSheet")?.classList.remove("hidden");
  renderGiftSheet();
}

function hideGiftSheet() {
  $("giftSheet")?.classList.add("hidden");
}

async function submitGiftPayment() {
  const tariff = getGiftTariff();
  if (state.giftTariffKey !== "devices" && !tariff) {
    showToast("Подарок не выбран");
    return;
  }
  if (!state.giftProvider) {
    showToast("Выберите способ оплаты");
    return;
  }
  if (state.giftRecipientStatus === "searching" || state.giftRecipientStatus === "typing") {
    showToast("Подождите проверку получателя");
    return;
  }
  if (state.giftRecipientCandidate && !state.giftRecipientSelected) {
    showToast("Выберите найденного получателя или очистите поле");
    return;
  }
  try {
    const result = await request("/api/gifts/payment", {
      method: "POST",
      body: JSON.stringify({
        provider: state.giftProvider,
        tariff_key: state.giftTariffKey === "devices" ? "devices" : tariff.key,
        count: Number(state.giftDeviceCount || 1),
        recipient: state.giftRecipientSelected?.tg_id || "",
        message: $("giftMessageInput")?.value || "",
        show_sender: Boolean($("giftShowSenderInput")?.checked),
      }),
    });
    if (result.payment_url) {
      state.giftCheckVisible = true;
      const tg = window.Telegram?.WebApp;
      if (tg?.openLink) tg.openLink(result.payment_url);
      else window.open(result.payment_url, "_blank", "noopener");
      $("giftStatus").textContent = "Оплата открыта. После подтверждения подарок появится у друга или придёт ссылка.";
      renderGiftSheet();
      bumpLiveRefresh();
      showToast(result.message || "Платеж создан");
      return;
    }
    if (result.dashboard) applyDashboardUpdate(result.dashboard, state.session, { force: true });
    const link = result.gift?.link || "";
    hideGiftSheet();
    showSuccessModal("Подарок оплачен", link ? "Ссылка отправлена вам в Telegram." : "Пользователь получил уведомление в боте.");
    showToast(result.message || "Подарок оплачен");
  } catch (error) {
    showToast(error.message);
  }
}

function getReferralShareUrl() {
  const referrals = state.dashboard?.referrals || {};
  const link = String(referrals.link || "").trim();
  if (!/^https?:\/\//i.test(link)) return "";
  const days = Number(referrals.trial_bonus_days || 4);
  const text = `Приглашаю тебя в Send VPN:\n\n${link}\n\nПолучи бесплатные ${days} дня доступа`;
  return `https://t.me/share/url?text=${encodeURIComponent(text)}`;
}

async function shareReferralLink() {
  const tg = window.Telegram?.WebApp;
  if (tg?.shareMessage) {
    try {
      const result = await request("/api/referrals/share-message", {
        method: "POST",
        body: "{}",
      });
      if (result.prepared_message_id) {
        tg.shareMessage(result.prepared_message_id, (sent) => {
          if (sent === false) showToast("Отправка отменена");
        });
        return;
      }
    } catch (error) {
      console.warn("Prepared referral share failed", error);
    }
  }

  const shareUrl = getReferralShareUrl();
  if (!shareUrl) {
    showToast("Реферальная ссылка пока недоступна");
    return;
  }
  const opened = window.Telegram?.WebApp?.openLink
    ? (window.Telegram.WebApp.openLink(shareUrl), true)
    : openExternalLink(shareUrl);
  if (!opened) showToast("Не удалось открыть шаринг");
}

function resetPurchaseUiAfterSuccess() {
  state.expandedPurchase = null;
  state.purchaseProvider = "";
  state.purchaseCollapseOpen = false;
  state.balanceCollapseOpen = false;
  state.purchaseCheckVisible = false;
  state.balanceCheckVisible = false;
  state.purchaseStartedAt = 0;
  state.purchaseStatus = "";
  stopCountdownTimer();
}

function successModalFromPurchase(result, fallbackMessage, checkTarget = "purchase") {
  if (result.payment_url || !result.dashboard) return null;
  const message = localizeMessage(result.message || fallbackMessage);
  if (checkTarget === "balance") {
    return { title: "Успешное пополнение", text: message };
  }
  if (state.expandedPurchase?.kind === "devices") {
    return { title: "Устройства добавлены", text: message };
  }
  return { title: "Подписка куплена", text: message };
}

function successModalFromPaymentDetails(details = []) {
  const item = Array.isArray(details) ? details[0] : null;
  if (!item) return null;
  return {
    title: item.title || "Оплата прошла успешно",
    text: item.message || "Данные обновлены.",
  };
}

function showSuccessFromEvents(events = []) {
  const success = successModalFromPaymentDetails(events);
  if (!success) return;
  resetPurchaseUiAfterSuccess();
  renderAll();
  showSuccessModal(success.title, success.text);
}

function profileInitial(name) {
  const trimmed = String(name || "").trim();
  return trimmed ? trimmed.charAt(0).toUpperCase() : "G";
}

function normalizeTelegramLink(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (raw.startsWith("@")) return `https://t.me/${raw.slice(1)}`;
  return raw;
}

// Trial gate is shown at most ONCE per device. After the first appearance —
// whether the user claimed it or just dismissed it — we remember the choice in
// localStorage and never show it again on this device.
const TRIAL_GATE_SEEN_KEY = "jutsovpn:trialGateSeen";
function trialGateSeen() {
  try { return localStorage.getItem(TRIAL_GATE_SEEN_KEY) === "1"; } catch { return false; }
}
function markTrialGateSeen() {
  try { localStorage.setItem(TRIAL_GATE_SEEN_KEY, "1"); } catch {}
}
function needsTrialGate() {
  if (trialGateSeen()) return false;
  const subscription = state.dashboard?.subscription || {};
  if (subscription.free_used) return false;
  return Boolean(state.session) && Boolean(subscription.needs_free_trial ?? (Number(subscription.days_left || 0) <= 0));
}

function getChannelUrl() {
  return state.config?.channel_url || "";
}

function getTourStorageKey() {
  const tgId = state.session?.tg_id || state.dashboard?.profile?.tg_id || "guest";
  return `sendvpn:onboarding:${tgId}`;
}

function dashboardSignature(dashboard) {
  if (!dashboard) return "";
  const subscription = dashboard.subscription || {};
  const balance = dashboard.balance || {};
  const meta = dashboard.meta || {};
  const devices = (dashboard.devices || []).map((device) => [
    device.id,
    device.platform,
    device.name,
    device.app_name,
    device.last_seen,
  ]);

  return JSON.stringify({
    balance: balance.amount || 0,
    subscription: {
      sub_url: subscription.sub_url || "",
      days_left: subscription.days_left || 0,
      expires_human: subscription.expires_human || "",
      devices_active: subscription.devices_active || 0,
      devices_max: subscription.devices_max || 0,
      traffic_used_bytes: subscription.traffic_used_bytes || 0,
      traffic_limit_bytes: subscription.traffic_limit_bytes || 0,
      tariff_name: subscription.tariff_name || "",
      tariff_total_days: subscription.tariff_total_days || 0,
      has_subscription: Boolean(subscription.has_subscription),
      free_used: Boolean(subscription.free_used),
    },
    devices,
    pending: meta.pending_payments_count || 0,
  });
}

function dashboardDiff(previous, next) {
  const prevSub = previous?.subscription || {};
  const nextSub = next?.subscription || {};
  const prevDevices = previous?.devices || [];
  const nextDevices = next?.devices || [];
  const prevDeviceIds = prevDevices.map((device) => String(device.id)).sort().join("|");
  const nextDeviceIds = nextDevices.map((device) => String(device.id)).sort().join("|");

  return {
    balance: Number(previous?.balance?.amount || 0) !== Number(next?.balance?.amount || 0),
    devices: prevDeviceIds !== nextDeviceIds || prevDevices.length !== nextDevices.length,
    subscription:
      prevSub.sub_url !== nextSub.sub_url ||
      Number(prevSub.days_left || 0) !== Number(nextSub.days_left || 0) ||
      Number(prevSub.devices_max || 0) !== Number(nextSub.devices_max || 0),
    traffic:
      Number(prevSub.traffic_used_bytes || 0) !== Number(nextSub.traffic_used_bytes || 0) ||
      Number(prevSub.traffic_limit_bytes || 0) !== Number(nextSub.traffic_limit_bytes || 0),
  };
}

function flashLiveUpdate(selectors) {
  if (state.prefersReducedMotion) return;

  requestAnimationFrame(() => {
    selectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach((node) => {
        node.classList.remove("live-updated");
        void node.offsetWidth;
        node.classList.add("live-updated");
        window.setTimeout(() => node.classList.remove("live-updated"), 900);
      });
    });
  });
}

function preservePendingDeviceDelete(nextDashboard) {
  const pendingId = state.pendingDeviceDelete;
  if (!pendingId) return null;
  return (nextDashboard?.devices || []).some((device) => String(device.id) === String(pendingId)) ? pendingId : null;
}

function applyDashboardUpdate(dashboard, session = state.session, { force = false, highlight = true } = {}) {
  if (!dashboard) return false;

  const signature = dashboardSignature(dashboard);
  if (!force && signature === state.liveRefreshLastSignature) return false;

  const previous = state.dashboard;
  const diff = dashboardDiff(previous, dashboard);
  const pendingDeviceDelete = preservePendingDeviceDelete(dashboard);

  state.session = session || state.session;
  state.dashboard = dashboard;
  state.pendingDeviceDelete = pendingDeviceDelete;
  state.liveRefreshLastSignature = signature;

  // Persist a copy so that on the very next page load we can immediately
  // paint the hero/profile with the real subscription data (expiry date,
  // sub_url, etc.) before /api/session resolves. This prevents the
  // "до DD месяца YYYY" line from briefly disappearing on revisit.
  saveCachedDashboard({ dashboard, session: state.session });

  renderAll();

  if (previous && highlight) {
    const selectors = [];
    if (diff.balance) selectors.push("#financeBalanceValue", "#balanceSectionBadge");
    if (diff.devices) selectors.push("#deviceList", "#deviceCounter");
    if (diff.subscription) selectors.push("#daysLeft", "#untilDate", ".copy-card", "#profileStatusValue", "#profileExpiresValue");
    if (diff.traffic) selectors.push(".traffic-card", "#profileTrafficValue");
    flashLiveUpdate(selectors);
  }

  return true;
}

function hasPendingPaymentWatch() {
  return Boolean(
    state.dashboard?.meta?.has_pending_payments ||
    state.dashboard?.meta?.pending_payments_count ||
    state.purchaseCheckVisible ||
    state.balanceCheckVisible
  );
}

function hasFastLiveWindow() {
  return Boolean(
    hasPendingPaymentWatch() ||
    Date.now() < state.liveRefreshFastUntil
  );
}

function hasSeenTour() {
  try {
    return window.localStorage?.getItem(getTourStorageKey()) === "done";
  } catch {
    return true;
  }
}

function markTourSeen() {
  try {
    window.localStorage?.setItem(getTourStorageKey(), "done");
  } catch {
    // localStorage can be unavailable in strict WebView modes.
  }
}

function shouldStartFirstRunTour(force = false) {
  // Hard rule: never run the tour while the trial gate is visible — they
  // must happen sequentially. The DOM is the source of truth here because
  // localStorage may already mark the gate "seen" while it's still on screen.
  const gate = document.getElementById("trialGate");
  if (gate && !gate.classList.contains("hidden")) return false;
  if (needsTrialGate()) return false;
  if (!force && hasSeenTour()) return false;
  if (force) return true;

  const subscription = state.dashboard?.subscription || {};
  return Boolean(state.session?.is_new_user || subscription.free_used);
}

function notifyProfileGateReady() {
  request("/api/bot/profile-gate", {
    method: "POST",
    body: "{}",
  }).catch((error) => {
    console.warn("Failed to update bot profile gate", error);
    try {
      window.Telegram?.WebApp?.sendData?.(JSON.stringify({ action: "profile_gate_ready" }));
    } catch (sendError) {
      console.warn("Failed to send profile gate event", sendError);
    }
  });
}

function openExternalLink(url) {
  const link = normalizeTelegramLink(url);
  if (!link) return false;
  const tg = window.Telegram?.WebApp;
  if (tg?.openTelegramLink && /^https?:\/\/t\.me\//i.test(link)) {
    tg.openTelegramLink(link);
    return true;
  }
  if (tg?.openLink) {
    tg.openLink(link);
    return true;
  }
  window.open(link, "_blank", "noopener");
  return true;
}

function renderProfileAvatar() {
  const node = $("profileAvatar");
  if (!node) return;

  const profile = state.dashboard?.profile || {};
  const name = profile.name || "Профиль";
  const photoUrl = String(profile.photo_url || "").trim();

  if (photoUrl) {
    node.innerHTML = `<img src="${escapeHtml(photoUrl)}" alt="${escapeHtml(name)}">`;
    node.setAttribute("aria-label", name);
    return;
  }

  node.textContent = profileInitial(name);
  node.setAttribute("aria-label", name);
}

function ensureLottieAnimation(key, containerId, path, options = {}) {
  const container = $(containerId);
  const current = state.animations[key];
  const renderer = options.renderer || "svg";

  if (!container || !window.lottie) {
    if (current) current.destroy();
    delete state.animations[key];
    return null;
  }

  if (current && current.__container === container && current.__path === path && current.__renderer === renderer) return current;

  if (current) current.destroy();

  const animation = window.lottie.loadAnimation({
    container,
    renderer,
    loop: Boolean(options.loop),
    autoplay: options.autoplay !== false,
    path,
    rendererSettings: {
      preserveAspectRatio: "xMidYMid meet",
      progressiveLoad: true,
      ...(options.rendererSettings || {}),
    },
  });

  if (typeof options.speed === "number") animation.setSpeed(options.speed);

  animation.__container = container;
  animation.__path = path;
  animation.__renderer = renderer;
  state.animations[key] = animation;
  return animation;
}

function resetAnimation(animation) {
  if (!animation) return;
  animation.stop();
  animation.goToAndStop(0, true);
}

function playAnimationOnce(animation) {
  if (!animation) return;
  animation.stop();
  animation.goToAndPlay(0, true);
}

function stopAnimationAtFrame(animation, frameRatio = 1) {
  if (!animation) return;

  const stop = () => {
    const lastFrame = Math.max(0, Math.floor(Number(animation.totalFrames || 1)) - 1);
    const targetFrame = Math.max(0, Math.min(lastFrame, Math.round(lastFrame * frameRatio)));
    animation.goToAndStop(targetFrame, true);
  };

  if (animation.isLoaded || animation.totalFrames) {
    stop();
    return;
  }

  const onLoaded = () => {
    animation.removeEventListener?.("DOMLoaded", onLoaded);
    stop();
  };
  animation.addEventListener?.("DOMLoaded", onLoaded);
}

function cleanupDeviceEmptyGirlObserver() {
  if (!state.deviceEmptyGirlObserver) return;
  state.deviceEmptyGirlObserver.disconnect();
  state.deviceEmptyGirlObserver = null;
}

function playDeviceEmptyGirlWhenVisible(animation) {
  const container = $("deviceEmptyGirl");
  cleanupDeviceEmptyGirlObserver();

  if (!container || !animation) return;

  animation.loop = false;
  state.deviceEmptyGirlPlayed = true;
  stopAnimationAtFrame(animation, 0.5);
}

function setLoadingProgress(value) {
  const normalized = Math.max(0, Math.min(100, Math.round(Number(value) || 0)));
  state.loadingProgress = normalized;
  $("loadingProgressFill").style.width = `${normalized}%`;
  $("loadingProgressText").textContent = `${normalized}%`;
}

function animateCollapse(body, willOpen) {
  if (!body) return;

  body.classList.add("is-animating");
  const content = body.firstElementChild;
  const contentHeight = content ? content.scrollHeight : body.scrollHeight;

  body.style.overflow = "hidden";

  if (willOpen) {
    body.classList.add("is-open");
    body.style.height = "0px";
    body.style.opacity = "0";
    body.style.marginTop = "0px";

    requestAnimationFrame(() => {
      body.style.height = `${contentHeight}px`;
      body.style.opacity = "1";
      body.style.marginTop = "12px";
    });
  } else {
    body.style.height = `${body.scrollHeight}px`;
    body.style.opacity = "1";
    body.style.marginTop = "12px";

    requestAnimationFrame(() => {
      body.style.height = "0px";
      body.style.opacity = "0";
      body.style.marginTop = "0px";
    });
  }

  const onEnd = (event) => {
    if (event.propertyName !== "height") return;
    body.removeEventListener("transitionend", onEnd);
    body.classList.remove("is-animating");

    if (willOpen) {
      body.style.height = "auto";
      body.style.overflow = "visible";
    } else {
      body.classList.remove("is-open");
      body.style.height = "0px";
    }
  };

  body.addEventListener("transitionend", onEnd);
}

function syncCollapseState(body, isOpen) {
  if (!body) return;
  body.classList.toggle("is-open", isOpen);
  body.style.overflow = isOpen ? "visible" : "hidden";
  body.style.height = isOpen ? "auto" : "0px";
  body.style.opacity = isOpen ? "1" : "0";
  body.style.marginTop = isOpen ? "12px" : "0px";
}

function clearLoadingProgressTimer() {
  if (!state.loadingProgressTimer) return;
  clearInterval(state.loadingProgressTimer);
  state.loadingProgressTimer = null;
}

function startLoadingScreen() {
  $("loadingScreen").classList.remove("is-hidden");
  ensureLottieAnimation("loading", "loadingEmoji", "/static/emoji_539552126079.json", {
    renderer: "svg",
    loop: true,
    autoplay: true,
    speed: state.prefersReducedMotion ? 0.7 : 0.9,
  });

  clearLoadingProgressTimer();
  setLoadingProgress(8);
  state.loadingProgressTimer = setInterval(() => {
    if (state.loadingProgress >= 90) return;
    setLoadingProgress(state.loadingProgress + (state.loadingProgress < 50 ? 6 : 3));
  }, 180);
}

async function finishLoadingScreen() {
  clearLoadingProgressTimer();
  setLoadingProgress(100);
  await new Promise((resolve) => setTimeout(resolve, 180));
  state.animations.loading?.destroy();
  delete state.animations.loading;
  $("loadingScreen").classList.add("is-hidden");
  $("appShell").classList.remove("app-hidden");
  $("appShell").classList.add("app-ready");
}

function formatRub(value) {
  return `${Number(value || 0).toLocaleString("ru-RU")}\u202F₽`;
}

function formatTraffic(bytes) {
  const value = Number(bytes || 0);
  if (!value) return "0 B";
  const units = ["B", "КБ", "МБ", "ГБ", "ТБ"];
  let amount = value;
  let index = 0;
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024;
    index += 1;
  }
  return `${amount.toFixed(index > 1 ? 2 : 0)} ${units[index]}`;
}

function getBalanceAmount() {
  return Number(state.dashboard?.balance?.amount || 0);
}

function hasPendingPayments() {
  return Boolean(state.dashboard?.meta?.has_pending_payments || Number(state.dashboard?.meta?.pending_payments_count || 0) > 0);
}

function getSubscriptionBatteryPath() {
  const subscription = state.dashboard?.subscription || {};
  const daysLeft = Number(subscription.days_left || 0);
  const totalDays = Number(subscription.tariff_total_days || 0);

  if (!subscription.has_subscription || daysLeft <= 0 || totalDays <= 0) {
    return BATTERY_EMOJI_PATHS[0];
  }

  const ratio = Math.max(0, Math.min(1, daysLeft / totalDays));
  if (ratio >= 0.75) return BATTERY_EMOJI_PATHS[3];
  if (ratio >= 0.5) return BATTERY_EMOJI_PATHS[2];
  if (ratio >= 0.25) return BATTERY_EMOJI_PATHS[1];
  return BATTERY_EMOJI_PATHS[0];
}

function renderLiveBattery() {
  const subscription = state.dashboard?.subscription || {};
  const daysLeft = Number(subscription.days_left || 0);
  const totalDays = Number(subscription.tariff_total_days || 0);
  const ratio = totalDays > 0 ? Math.max(0, Math.min(1, daysLeft / totalDays)) : 0;
  const batteryPercent = Math.round(ratio * 100);
  const label = subscription.has_subscription && daysLeft > 0
    ? `Осталось ${daysLeft} дн. из ${totalDays} дн. (${subscription.tariff_name || "тариф"})`
    : "Подписка неактивна";

  $("liveBadge")?.setAttribute("aria-label", label);
  $("liveBadgeEmoji")?.setAttribute("title", subscription.has_subscription && daysLeft > 0 ? `${batteryPercent}%` : "0%");
  ensureLottieAnimation("liveBattery", "liveBadgeEmoji", getSubscriptionBatteryPath(), {
    renderer: "svg",
    loop: false,
    autoplay: true,
    speed: state.prefersReducedMotion ? 0.7 : 0.85,
  });
}

function syncPendingPaymentButtons() {
  const button = $("balanceCheckPaymentsButton");
  if (!button) return;

  const visible = state.balanceCheckVisible;
  button.classList.toggle("hidden", !visible);
  button.textContent = "Проверить оплату";
}

function getDeviceCapacityLeft() {
  const currentMax = Number(state.dashboard?.subscription?.devices_max || 0);
  return Math.max(0, MAX_ACCOUNT_DEVICES - currentMax);
}

function getDeviceTitle(device) {
  const appName = String(device.app_name || "").trim();
  const platform = String(device.platform || "").trim();
  return appName || platform || "Устройство";
}

function getDeviceSubtitle(device) {
  const platform = String(device.platform || "").trim();
  const lastSeen = String(device.last_seen || "").trim();
  const title = getDeviceTitle(device);
  const parts = [];

  if (platform && platform !== title) parts.push(platform);
  if (lastSeen && lastSeen !== "—") parts.push(lastSeen);

  return parts.join(" • ") || "Подключено к аккаунту";
}

function getProviderLabel(provider) {
  return {
    balance: "Оплатить с баланса",
    sbp: "СБП",
    card: "Карта",
    crypto: "CryptoBot",
  }[provider] || provider;
}

function providerOptions(includeBalance, amount) {
  const providers = state.config?.providers || {};
  const result = [];

  if (includeBalance && providers.balance && getBalanceAmount() >= Number(amount || 0)) {
    result.push("balance");
  }
  if (providers.sbp) result.push("sbp");
  if (providers.card) result.push("card");
  if (providers.crypto) result.push("crypto");
  return result;
}

function firstSubscriptionLink(source) {
  return String(source || "").split(/\s+/).find(Boolean) || "";
}

function canOpenDirectLink(url) {
  return /^(https?:\/\/|tg:\/\/|vless:\/\/|vmess:\/\/|ss:\/\/|trojan:\/\/)/i.test(url);
}

function openWebAppFullscreen() {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;

  try {
    tg.ready();
    tg.expand();
    tg.setHeaderColor("#090909");
    tg.setBackgroundColor("#090909");
    if (typeof tg.disableVerticalSwipes === "function") tg.disableVerticalSwipes();
    if (typeof tg.requestFullscreen === "function") tg.requestFullscreen();
  } catch (error) {
    console.warn("fullscreen", error);
  }
}

async function ensureTelegramWebAppSession() {
  const tg = window.Telegram?.WebApp;
  if (!tg?.initData) return false;

  try {
    await request("/api/auth/telegram-webapp", {
      method: "POST",
      body: JSON.stringify({ initData: tg.initData, init_data: tg.initData }),
    });
    return true;
  } catch (error) {
    showToast(error.message);
    return false;
  }
}

function setBrowserAuthGate(visible) {
  const gate = $("browserAuthGate");
  if (!gate) return;
  gate.classList.toggle("hidden", !visible);
  document.body.classList.toggle("browser-auth-required", visible);
  // Hide the loading screen and the entire app shell when the gate is up so
  // the dashboard never flashes for non-Telegram visitors.
  const loading = $("loadingScreen");
  if (loading) loading.classList.toggle("hidden", visible);
  const shell = $("appShell");
  if (shell) {
    shell.classList.toggle("app-hidden", visible);
    shell.style.display = visible ? "none" : "";
  }
}

function installTelegramLoginWidget() {
  // Telegram login widget removed: site is Telegram-only. Just point the
  // fallback link to the bot.
  const fallback = $("telegramBotFallback");
  const username = state.config?.bot_username;
  if (fallback && username) {
    fallback.href = `https://t.me/${username}`;
  }
}

function switchTab(tab) {
  if (state.activeTab !== tab) logEvent("tab_click", tab);
  state.activeTab = tab;
  const mapping = {
    home: "homeView",
    buy: "buyView",
    finance: "financeView",
    profile: "profileView",
  };

  Object.entries(mapping).forEach(([key, id]) => {
    $(id).classList.toggle("hidden", key !== tab);
  });

  document.querySelectorAll(".tabbar-item").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tab === tab);
  });

  const activePanel = $(mapping[tab]);
  if (activePanel) activePanel.scrollTop = 0;
  const screen = document.querySelector(".screen");
  if (screen) screen.scrollTop = 0;
  window.scrollTo(0, 0);

  playTabAnimationOnce(tab);
  if (state.tourActive) renderTour();
}

function openSettingsSheet() {
  state.settingsOpen = true;
  $("settingsSheet")?.classList.remove("hidden");
  renderSettingsPanel();
}

function closeSettingsSheet() {
  state.settingsOpen = false;
  $("settingsSheet")?.classList.add("hidden");
}

function renderSettingsPanel() {
  const status = $("settingsStatus");
  if (status && !status.dataset.ready) {
    status.textContent = "Можно обновить профиль или завершить все активные сессии.";
    status.dataset.ready = "1";
  }
}

async function refreshProfileFromTelegram() {
  const status = $("settingsStatus");
  try {
    const result = await request("/api/session/refresh-profile", {
      method: "POST",
      body: "{}",
    });
    if (result.dashboard) {
      applyDashboardUpdate(result.dashboard, state.session, { force: true });
      renderAll();
    }
    if (status) status.textContent = "Профиль обновлен из Telegram.";
    showToast("Данные профиля обновлены");
  } catch (error) {
    if (status) status.textContent = error.message || "Не удалось обновить профиль.";
    showToast(error.message || "Не удалось обновить профиль");
  }
}

async function logoutAllSessions() {
  const status = $("settingsStatus");
  try {
    await request("/api/session/logout-all", {
      method: "POST",
      body: "{}",
    });
    if (status) status.textContent = "Все сессии завершены. Войдите снова.";
    showToast("Все сессии завершены");
    await logout();
  } catch (error) {
    if (status) status.textContent = error.message || "Не удалось завершить сессии.";
    showToast(error.message || "Не удалось завершить сессии");
  }
}

function syncAccessState() {
  const gated = needsTrialGate();
  const shell = $("appShell");
  const gate = $("trialGate");
  if (!shell || !gate) return;

  shell.classList.toggle("trial-mode", gated);
  gate.classList.toggle("hidden", !gated);
  if (gated) {
    state.tourActive = false;
    document.body.classList.remove("tour-active");
    renderTrialGate();
    // Remember that we've shown the gate — never show it again on this device.
    markTrialGateSeen();
    logEvent("trial_gate_shown", "first_run");
  }
}

function renderTrialGate() {
  const title = document.querySelector("#trialGate h2");
  const claimButton = $("trialClaimButton");
  const channelBlock = $("trialChannelBlock");
  if (!claimButton || !channelBlock) return;

  if (title) title.textContent = "Получить 3 дня бесплатной подписки";

  const needsChannel = state.trialStep === "channel";
  channelBlock.classList.toggle("hidden", !needsChannel);
  claimButton.textContent = needsChannel ? "Активировать" : "Получить";
}

async function claimFreeTrial() {
  const button = $("trialClaimButton");
  if (button) button.disabled = true;

  try {
    const result = await request("/api/free-trial", {
      method: "POST",
      body: "{}",
    });
    state.trialStep = "intro";
    applyDashboardUpdate(result.dashboard, state.session, { force: true });
    bumpLiveRefresh();
    switchTab("home");
    showToast("Триал активирован — подписка на 3 дня");
    // Sequential UX: trial activation first, then a short pause so the user
    // can see the home screen, only then start the guided tour.
    setTimeout(() => startFirstRunTourIfNeeded(true), 1200);
  } catch (error) {
    if (error.message === "channel_required") {
      state.trialStep = "channel";
      renderTrialGate();
      showToast("Подпишитесь на канал и нажмите активировать");
      return;
    }
    showToast(error.message);
  } finally {
    if (button) button.disabled = false;
  }
}

function startFirstRunTourIfNeeded(force = false) {
  if (!shouldStartFirstRunTour(force)) return;
  state.tourActive = true;
  state.tourStep = 0;
  switchTab(TOUR_STEPS[0].tab);
  renderTour();
}

function finishTour({ goHome = false } = {}) {
  state.tourActive = false;
  markTourSeen();
  notifyProfileGateReady();
  document.body.classList.remove("tour-active");
  $("tourOverlay")?.classList.add("hidden");
  document.querySelectorAll(".tabbar-item").forEach((button) => button.classList.remove("is-tour-target"));
  if (goHome) switchTab("home");
  maybeShowPushPrompt();
}

function nextTourStep() {
  if (state.tourStep >= TOUR_STEPS.length - 1) {
    finishTour({ goHome: true });
    return;
  }
  state.tourStep += 1;
  switchTab(TOUR_STEPS[state.tourStep].tab);
  renderTour();
}

function renderTour() {
  const overlay = $("tourOverlay");
  if (!overlay) return;

  if (!state.tourActive) {
    overlay.classList.add("hidden");
    document.body.classList.remove("tour-active");
    return;
  }

  const step = TOUR_STEPS[state.tourStep] || TOUR_STEPS[0];
  document.body.classList.add("tour-active");
  overlay.classList.remove("hidden");
  $("tourKicker").textContent = `${state.tourStep + 1} / ${TOUR_STEPS.length}`;
  $("tourTitle").textContent = t(step.titleKey);
  $("tourText").textContent = t(step.textKey);
  $("tourNextButton").textContent = state.tourStep === TOUR_STEPS.length - 1 ? t("tour_done") : t("tour_next");

  document.querySelectorAll(".tabbar-item").forEach((button) => {
    button.classList.toggle("is-tour-target", button.dataset.tab === step.tab);
  });
}

function playTabAnimationOnce(tab) {
  ["featured", "connect", "copy", "settings"].forEach((key) => {
    resetAnimation(state.animations[key]);
  });

  if (tab === "buy") {
    playAnimationOnce(state.animations.featured);
  }
}

function renderHero() {
  const dashboard = state.dashboard || {};
  const subscription = dashboard.subscription || {};
  const daysLeft = Number(subscription.days_left || 0);
  const isActive = Boolean(subscription.has_subscription && daysLeft > 0);
  const trafficUsed = formatTraffic(subscription.traffic_used_bytes);
  const trafficLimitBytes = Number(subscription.traffic_limit_bytes || 0);
  const isUnlimitedTraffic = isActive && trafficLimitBytes <= 0;
  const trafficLimit = isUnlimitedTraffic ? "∞" : formatTraffic(trafficLimitBytes);

  $("daysLeft").textContent = String(daysLeft);
  // Show expiry date whenever the backend says the subscription is still active,
  // even if days_left rounded down to 0 (e.g. last day of a trial). When we
  // have real data, drop the data-i18n attribute so applyTranslations() won't
  // overwrite the date with the static "нет активной подписки" placeholder.
  const untilEl = $("untilDate");
  if (untilEl) {
    if (subscription.has_subscription) {
      untilEl.textContent = `до ${subscription.expires_human || "—"}`;
      untilEl.removeAttribute("data-i18n");
    } else if (subscription.expires_human) {
      untilEl.textContent = `истекла ${subscription.expires_human}`;
      untilEl.removeAttribute("data-i18n");
    } else {
      untilEl.textContent = t("hero_no_sub") || "нет активной подписки";
      untilEl.setAttribute("data-i18n", "hero_no_sub");
    }
  }
  $("trafficUsed").textContent = trafficUsed;
  $("trafficLimit").textContent = `/ ${trafficLimit}`;
  if ($("trafficHint")) $("trafficHint").textContent = `${trafficUsed} использовано`;
  if ($("trafficMode")) $("trafficMode").textContent = isUnlimitedTraffic ? "Безлимит" : "Лимит";
  $("deviceCounter").textContent = `${subscription.devices_active || 0} / ${subscription.devices_max || 0}`;
  const financeBalance = formatRub(dashboard.balance?.amount);
  if ($("balanceSectionBadge")) $("balanceSectionBadge").textContent = financeBalance;
  if ($("financeBalanceValue")) $("financeBalanceValue").textContent = financeBalance;
  $("profileName").textContent = dashboard.profile?.name || "Профиль";
  $("roleBadge").textContent = dashboard.profile?.is_admin ? "admin" : "user";
  renderProfileAvatar();
  // Profile -> "Ссылка подписки": always render the value as a clickable link
  // pointing at the /sub subscription page. Whether the key has been issued
  // or not, tapping the text opens the same dynamic page in the in-app
  // browser.
  const profileKeyEl = $("profileKey");
  if (profileKeyEl) {
    const subPagePath = state.config?.sub_page_url || "/sub";
    const subPageUrl = /^https?:\/\//i.test(subPagePath) ? subPagePath : new URL(subPagePath, location.origin).toString();
    if (subscription.sub_url) {
      profileKeyEl.innerHTML = `<a class="profile-sub-link-active" href="${escapeHtml(subPageUrl)}" target="_blank" rel="noopener" data-sub-page-link="true">${escapeHtml(subscription.sub_url)}</a>`;
      profileKeyEl.dataset.subUrl = "1";
    } else {
      const label = t("sub_link_pending") || "Ключ пока не выдан";
      profileKeyEl.innerHTML = `<a class="profile-sub-link-pending" href="${escapeHtml(subPageUrl)}" target="_blank" rel="noopener" data-sub-page-link="true">${escapeHtml(label)}</a>`;
      profileKeyEl.dataset.subUrl = "0";
    }
  }
  $("profileStatusValue").textContent = isActive ? "● Активна" : "● Неактивна";
  $("profileExpiresValue").textContent = subscription.expires_human || "—";
  $("profileTrafficValue").textContent = `${trafficUsed} / ${trafficLimit}`;
  if ($("profileTelegramIdValue")) $("profileTelegramIdValue").textContent = dashboard.profile?.tg_id || state.session?.tg_id || "—";
  if ($("profileLoginValue")) $("profileLoginValue").textContent = state.session ? "Telegram" : "—";
  renderReferralSheet();
  renderLiveBattery();
}

function renderDevices() {
  const target = $("deviceList");
  const devices = state.dashboard?.devices || [];
  const subscriptionUrl = String(state.dashboard?.subscription?.sub_url || "").trim();

  if (!devices.length) {
    cleanupDeviceEmptyGirlObserver();
    if (state.animations.deviceEmptyGirl) {
      state.animations.deviceEmptyGirl.destroy();
      delete state.animations.deviceEmptyGirl;
    }
    const emptyImg = state.config?.empty_image_url || "https://i.ibb.co/5XgDpWSf/Chat-GPT-Image-30-2026-17-18-25.png";
    target.innerHTML = `
      <article class="device-item device-item-empty">
        ${emptyImg ? `<img class="device-empty-girl" src="${escapeHtml(emptyImg)}" alt="" aria-hidden="true">` : ""}
        <div class="device-empty-copy">
          <div class="device-title">${t("empty_yet")}</div>
          ${subscriptionUrl ? `
            <a class="device-subtitle device-empty-link" href="${escapeHtml(subscriptionUrl)}" target="_blank" rel="noopener" data-subscription-link="true">${t("tap_to_connect")}</a>
          ` : `
            <div class="device-subtitle device-empty-link is-disabled">${t("tap_to_connect")}</div>
          `}
        </div>
      </article>
    `;
    return;
  }

  cleanupDeviceEmptyGirlObserver();
  if (state.animations.deviceEmptyGirl) {
    state.animations.deviceEmptyGirl.destroy();
    delete state.animations.deviceEmptyGirl;
  }

  target.innerHTML = devices.map((device) => {
    const icon = deviceIconsWhite[(device.platform || "").toLowerCase()] || deviceIconsWhite.default;
    const title = escapeHtml(getDeviceTitle(device));
    const subtitle = escapeHtml(getDeviceSubtitle(device));
    const isConfirming = state.pendingDeviceDelete === String(device.id);
    return `
      <article class="device-item ${isConfirming ? "is-confirming" : ""}">
        <div class="device-icon">${icon}</div>
        <div class="device-main">
          ${isConfirming ? `
            <div class="device-confirm-text">Вы точно хотите удалить устройство?</div>
          ` : `
            <div class="device-title">${title}</div>
            <div class="device-subtitle">${subtitle}</div>
          `}
        </div>
        ${isConfirming ? `
          <div class="device-confirm-buttons">
            <button class="device-confirm-button confirm-cancel" type="button" data-device-cancel="${escapeHtml(device.id)}" aria-label="Отменить удаление">✕</button>
            <button class="device-confirm-button confirm-accept" type="button" data-device-confirm="${escapeHtml(device.id)}" aria-label="Удалить устройство">✓</button>
          </div>
        ` : `<button class="device-remove" type="button" data-device="${escapeHtml(device.id)}">✕</button>`}
      </article>
    `;
  }).join("");

  target.querySelectorAll("[data-device]").forEach((button) => {
    button.addEventListener("click", () => {
      state.pendingDeviceDelete = String(button.dataset.device);
      renderDevices();
    });
  });

  target.querySelectorAll("[data-device-cancel]").forEach((button) => {
    button.addEventListener("click", () => {
      state.pendingDeviceDelete = null;
      renderDevices();
    });
  });

  target.querySelectorAll("[data-device-confirm]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const result = await request(`/api/devices/${encodeURIComponent(button.dataset.deviceConfirm)}`, { method: "DELETE" });
        state.pendingDeviceDelete = null;
        applyDashboardUpdate(result.dashboard, state.session, { force: true });
        bumpLiveRefresh(20000);
        showToast(result.message || "Устройство удалено");
      } catch (error) {
        showToast(error.message);
      }
    });
  });
}

function currentPurchaseCountdown() {
  if (!state.purchaseStartedAt) return "15:00";
  const remainingMs = Math.max(0, PAYMENT_TTL_MS - (Date.now() - state.purchaseStartedAt));
  const minutes = String(Math.floor(remainingMs / 60000)).padStart(2, "0");
  const seconds = String(Math.floor((remainingMs % 60000) / 1000)).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function getTariffByKey(key) {
  return (state.config?.tariffs || []).find((tariff) => tariff.key === key) || null;
}

function currentPurchaseAmount() {
  if (!state.expandedPurchase) return 0;
  if (state.expandedPurchase.kind === "tariff") {
    return Number(getTariffByKey(state.expandedPurchase.tariffKey)?.rub || 0);
  }
  if (state.expandedPurchase.kind === "devices") {
    return Number(state.config?.extra_device_rub || 0) * Number(state.expandedPurchase.count || 1);
  }
  return 0;
}

function ensurePurchaseProvider(amount) {
  const providers = providerOptions(true, amount);
  if (!providers.length) {
    state.purchaseProvider = "";
    return "";
  }
  if (!providers.includes(state.purchaseProvider)) {
    state.purchaseProvider = "";
  }
  return state.purchaseProvider;
}

function updatePaymentMethodLabels(buttons, selectedButton) {
  buttons.forEach((item) => {
    const isSelected = item === selectedButton;
    item.classList.toggle("is-selected", isSelected);
    const meta = item.querySelector(".payment-method-meta");
    if (meta) meta.textContent = isSelected ? "Выбран" : "Выбрать";
  });
}

function renderPurchaseMethods(amount) {
  const providers = providerOptions(true, amount);
  if (!providers.length) {
    return `<div class="purchase-status">Нет доступных способов оплаты</div>`;
  }

  const selectedProvider = ensurePurchaseProvider(amount);
  return providers.map((provider) => `
    <button class="payment-method purchase-provider-button ${provider === selectedProvider ? "is-selected" : ""}" type="button" data-provider="${provider}">
      <span class="payment-method-label">${getProviderLabel(provider)}</span>
      <strong class="payment-method-meta">${provider === selectedProvider ? "Выбран" : "Выбрать"}</strong>
    </button>
  `).join("");
}

function renderPaymentCollapseIcon() {
  return `
    <span class="payment-collapse-icon" aria-hidden="true">
      <div id="purchaseCollapseEmoji"></div>
    </span>
  `;
}

function renderInlinePurchasePanel(title, subtitle, amount) {
  const selectedProvider = ensurePurchaseProvider(amount);
  const checkButton = state.purchaseCheckVisible
    ? `<button class="cta cta-secondary cta-small" id="purchaseCheckButton" type="button">Проверить оплату</button>`
    : "";
  const countdown = state.purchaseStartedAt
    ? `<span class="countdown" id="purchaseCountdown">${currentPurchaseCountdown()}</span>`
    : `<span class="countdown countdown-hidden" id="purchaseCountdown"></span>`;
  const collapseIcon = renderPaymentCollapseIcon();
  return `
    <div class="purchase-panel">
      <div class="purchase-panel-head">
        <div>
          <span class="label">Оплата</span>
          <div class="purchase-title">${title}</div>
          <div class="purchase-subtitle">${subtitle}</div>
        </div>
        <button class="icon-btn purchase-close-button" type="button" aria-label="Закрыть">✕</button>
      </div>
      <div class="purchase-inline-meta">
        <span>К оплате ${formatRub(amount)}</span>
        ${countdown}
      </div>
      <div class="purchase-actions">
        <button class="payment-collapse ${state.purchaseCollapseOpen ? "is-open" : ""}" id="purchaseCollapseToggle" type="button">
          <span>Способы оплаты</span>
          ${collapseIcon}
        </button>
        <div class="payment-collapse-body ${state.purchaseCollapseOpen ? "is-open" : ""}" id="purchaseCollapseBody">
          <div class="payment-methods">${renderPurchaseMethods(amount)}</div>
        </div>
        <button class="cta cta-primary cta-small" id="purchasePayButton" type="button" ${selectedProvider ? "" : "disabled"}>
          Оплатить
        </button>
        ${checkButton}
        <div class="purchase-status" id="purchaseStatus">${state.purchaseStatus || "Выберите способ оплаты и нажмите оплатить."}</div>
      </div>
    </div>
  `;
}

function renderTariffPrice(tariff) {
  const original = Number(tariff.original_rub || tariff.rub || 0);
  const current = Number(tariff.rub || 0);
  if (tariff.has_discount && original > current) {
    return `
      <strong class="plan-price plan-price-sale">
        <span class="old-price">${formatRub(original)}</span>
        <span class="new-price">${formatRub(current)}</span>
      </strong>
    `;
  }
  return `<strong class="plan-price">${formatRub(current)}</strong>`;
}

function renderTariffs() {
  const target = $("tariffList");
  const tariffs = state.config?.tariffs || [];
  // preserve initial static HTML so we can restore it when config is empty
  if (typeof renderTariffs._initialHtml === "undefined") {
    renderTariffs._initialHtml = target ? target.innerHTML : "";
  }

  // If no tariffs are provided by config, restore initial static markup and bind handlers
  if (!tariffs.length) {
    if (target) target.innerHTML = renderTariffs._initialHtml;
    bindStaticPlanButtons();
    return;
  }

  target.innerHTML = tariffs.map((tariff) => {
    const isExpanded = state.expandedPurchase?.kind === "tariff" && state.expandedPurchase.tariffKey === tariff.key;
    const inlinePanel = isExpanded
      ? renderInlinePurchasePanel(
          tariff.name,
          `${tariff.days} дней / ${tariff.devices} устройства`,
          Number(tariff.rub || 0),
        )
      : "";

    return `
      <article class="buy-card plan-card ${tariff.key === "3m" ? "is-featured" : ""}">
        ${tariff.key === "3m" ? '<div class="plan-card-featured-badge"><div id="featuredTariffEmoji"></div></div>' : ""}
        <div class="plan-top">
          <div>
            <span class="label">${t("tariff_label")}</span>
            <div class="plan-name">${tariff.name}</div>
          </div>
          ${renderTariffPrice(tariff)}
        </div>
        <div class="plan-meta">
          <span>${t("days_n", { n: tariff.days })}</span>
          <span>${t("devices_n", { n: tariff.devices })}</span>
          ${tariff.has_discount && tariff.discount ? `<span class="sale-badge">${t("sale")} ${tariff.discount.label}</span>` : ""}
        </div>
        <div class="plan-actions">
          <button class="cta cta-primary tariff-buy-button" type="button" data-tariff="${tariff.key}">
            ${t("buy")}
          </button>
          <button class="cta cta-secondary tariff-gift-button" type="button" data-tariff="${tariff.key}">
            ${t("gift")}
          </button>
        </div>
        ${inlinePanel}
      </article>
    `;
  }).join("");

  target.querySelectorAll(".tariff-buy-button").forEach((button) => {
    button.addEventListener("click", () => {
      const tariff = getTariffByKey(button.dataset.tariff);
      if (!tariff) return;
      logEvent("buy_click", tariff.key, { tariff: tariff.key, price_rub: tariff.price_rub });
      state.expandedPurchase = { kind: "tariff", tariffKey: tariff.key };
      state.purchaseProvider = "";
      state.purchaseCollapseOpen = false;
      state.purchaseCheckVisible = false;
      state.purchaseStartedAt = 0;
      state.purchaseStatus = "";
      renderTariffs();
      renderDevicePurchaseCard();
      bindInlinePurchaseEvents();
      button.closest(".plan-card")?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });

  target.querySelectorAll(".tariff-gift-button").forEach((button) => {
    button.addEventListener("click", () => {
      const tariff = getTariffByKey(button.dataset.tariff);
      if (!tariff) return;
      logEvent("gift_click", tariff.key, { tariff: tariff.key });
      showGiftSheet(tariff.key);
    });
  });

  ensureLottieAnimation("featured", "featuredTariffEmoji", "/static/emoji_534609287448.json", {
    renderer: "svg",
    loop: false,
    autoplay: false,
    speed: state.prefersReducedMotion ? 0.7 : 0.85,
  });
}

// Attach click handlers to static plan cards that exist in the HTML before any config is loaded.
function bindStaticPlanButtons() {
  document.querySelectorAll('#tariffList [data-tariff]').forEach((button) => {
    // avoid double-binding
    if (button.dataset._bound === '1') return;
    button.dataset._bound = '1';
    button.addEventListener('click', (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const key = button.dataset.tariff;
      const isGift = button.classList.contains('cta-secondary') || button.classList.contains('tariff-gift-button');
      const tariff = getTariffByKey(key) || ensureTariffFromDom(key, button);
      if (!tariff) return;
      if (isGift) {
        showGiftSheet(tariff.key);
        return;
      }
      if (!state.config) state.config = {};
      if (!state.config.providers || Object.keys(state.config.providers).length === 0) {
        state.config.providers = { sbp: true, card: true, crypto: true, balance: true };
      }
      state.expandedPurchase = { kind: 'tariff', tariffKey: tariff.key };
      state.purchaseProvider = '';
      state.purchaseCollapseOpen = false;
      state.purchaseCheckVisible = false;
      state.purchaseStartedAt = 0;
      state.purchaseStatus = '';
      renderTariffs();
      renderDevicePurchaseCard();
      bindInlinePurchaseEvents();
      button.closest('.plan-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });
}

function renderDevicePurchaseCard() {
  const target = $("devicePurchaseCard");
  const extraPrice = Number(state.config?.extra_device_rub || 0);
  const capacityLeft = getDeviceCapacityLeft();
  const currentMax = Number(state.dashboard?.subscription?.devices_max || 0);
  const expanded = state.expandedPurchase?.kind === "devices";
  const selectedCount = Math.min(Math.max(Number(state.expandedPurchase?.count || 1), 1), Math.max(capacityLeft, 1));
  const amount = extraPrice * selectedCount;
  const checkButton = state.purchaseCheckVisible
    ? `<button class="cta cta-secondary cta-small" id="purchaseCheckButton" type="button">Проверить оплату</button>`
    : "";
  const collapseIcon = renderPaymentCollapseIcon();

  target.innerHTML = `
    <article class="buy-card device-buy-card">
      <div class="device-purchase-head">
        <div>
          <div class="plan-name">Доп. устройство</div>
        </div>
        <strong class="plan-price">${formatRub(extraPrice)}</strong>
      </div>
      <div class="plan-actions">
        <button class="cta cta-primary" id="deviceExpandButton" type="button" ${capacityLeft <= 0 ? "disabled" : ""}>
          Купить
        </button>
        <button class="cta cta-secondary" id="deviceGiftButton" type="button">
          Подарить
        </button>
      </div>
      ${expanded ? `
        <div class="purchase-panel">
          <div class="purchase-panel-head">
            <div>
              <span class="label">Устройства</span>
              <div class="purchase-title">Доп. устройство</div>
              <div class="purchase-subtitle">Выберите количество</div>
            </div>
            <button class="icon-btn purchase-close-button" type="button" aria-label="Закрыть">✕</button>
          </div>
          <div class="device-purchase-controls">
            <div class="device-count-panel">
              <div class="range-output" id="deviceCountOutput">${selectedCount}</div>
              <div class="device-allowance">Лимит после оплаты: ${currentMax + selectedCount}</div>
            </div>
            <input class="device-range" id="deviceRange" type="range" min="1" max="${Math.max(capacityLeft, 1)}" value="${selectedCount}">
            <div class="purchase-inline-meta">
              <span>${selectedCount} × ${formatRub(extraPrice)}</span>
              ${state.purchaseStartedAt
                ? `<span class="countdown" id="purchaseCountdown">${currentPurchaseCountdown()}</span>`
                : `<span class="countdown countdown-hidden" id="purchaseCountdown"></span>`}
            </div>
            <button class="payment-collapse ${state.purchaseCollapseOpen ? "is-open" : ""}" id="purchaseCollapseToggle" type="button">
              <span>Способы оплаты</span>
              ${collapseIcon}
            </button>
            <div class="payment-collapse-body ${state.purchaseCollapseOpen ? "is-open" : ""}" id="purchaseCollapseBody">
              <div class="payment-methods">${renderPurchaseMethods(amount)}</div>
            </div>
            <button class="cta cta-primary cta-small" id="purchasePayButton" type="button" ${ensurePurchaseProvider(amount) ? "" : "disabled"}>
              Оплатить
            </button>
            ${checkButton}
            <div class="purchase-status" id="purchaseStatus">${state.purchaseStatus || "Выберите способ оплаты и нажмите оплатить."}</div>
          </div>
        </div>
      ` : ""}
    </article>
  `;

  $("deviceExpandButton")?.addEventListener("click", () => {
    if (capacityLeft <= 0) return;
    state.expandedPurchase = { kind: "devices", count: 1 };
    state.purchaseProvider = "";
    state.purchaseCollapseOpen = false;
    state.purchaseCheckVisible = false;
    state.purchaseStartedAt = 0;
    state.purchaseStatus = "";
    renderDevicePurchaseCard();
    renderTariffs();
    bindInlinePurchaseEvents();
    $("devicePurchaseCard")?.scrollIntoView({ behavior: "smooth", block: "center" });
  });

  $("deviceGiftButton")?.addEventListener("click", () => {
    showGiftSheet("devices", 1);
  });

  const range = $("deviceRange");
  if (range) {
    range.addEventListener("input", () => {
      state.expandedPurchase.count = Number(range.value);
      updateDevicePurchasePreview();
    });
  }
}

function updateDevicePurchasePreview() {
  if (state.expandedPurchase?.kind !== "devices") return;

  const currentMax = Number(state.dashboard?.subscription?.devices_max || 0);
  const extraPrice = Number(state.config?.extra_device_rub || 0);
  const selectedCount = Number(state.expandedPurchase.count || 1);
  const amount = extraPrice * selectedCount;

  $("deviceCountOutput").textContent = String(selectedCount);
  const allowance = document.querySelector(".device-allowance");
  if (allowance) allowance.textContent = `Лимит после оплаты: ${currentMax + selectedCount}`;

  const meta = document.querySelector(".purchase-inline-meta span");
  if (meta) meta.textContent = `${selectedCount} × ${formatRub(extraPrice)}`;

  const methods = document.querySelector("#purchaseCollapseBody .payment-methods");
  if (methods) methods.innerHTML = renderPurchaseMethods(amount);

  bindPurchaseMethodEvents();
}

function renderBalanceProviders() {
  const target = $("balanceProviderList");
  const payButton = $("balancePayButton");
  const amount = Number(document.querySelector('#balanceForm input[name="amount"]')?.value || 100);
  const providers = providerOptions(false, amount);

  if (payButton) payButton.disabled = true;

  target.innerHTML = providers.map((provider) => `
    <button class="payment-method balance-provider-button" type="button" data-provider="${provider}">
      <span class="payment-method-label">${getProviderLabel(provider)}</span>
      <strong class="payment-method-meta">Выбрать</strong>
    </button>
  `).join("");

  target.querySelectorAll(".balance-provider-button").forEach((button) => {
    button.addEventListener("click", () => {
      updatePaymentMethodLabels(target.querySelectorAll(".balance-provider-button"), button);
      if (payButton) payButton.disabled = false;
    });
  });
}

function renderAdmin() {
  const card = $("adminCard");
  if (!card) return;

  if (!state.dashboard?.profile?.is_admin) {
    card.classList.add("hidden");
    return;
  }

  card.classList.remove("hidden");
  $("adminStats").innerHTML = `
    <div>Пользователь: ${state.dashboard.profile.name}</div>
    <div>Telegram ID: ${state.dashboard.profile.tg_id}</div>
    <div>Тариф: ${state.dashboard.subscription.tariff_name || "—"}</div>
    <div>Баланс: ${formatRub(state.dashboard.balance.amount)}</div>
  `;
}

async function submitAdminBroadcast(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const text = String(form.get("text") || "").trim();
  const title = String(form.get("title") || "JutsoVPN").trim();
  const url = String(form.get("url") || "/cabinet").trim();
  const status = $("adminBroadcastStatus");
  if (!text) {
    showToast("Введите текст рассылки");
    return;
  }
  if (status) status.textContent = "Отправляем...";
  try {
    const result = await request("/api/admin/broadcast", {
      method: "POST",
      body: JSON.stringify({
        text,
        push_title: title,
        push_body: text.replace(/<[^>]+>/g, ""),
        push_url: url || "/cabinet",
        button_text: /^https?:\/\//i.test(url) || /^tg:\/\//i.test(url) ? "Открыть" : "",
        button_url: url,
        telegram: Boolean(form.get("telegram")),
        push: Boolean(form.get("push")),
      }),
    });
    const message = `Telegram: ${result.sent || 0}/${(result.sent || 0) + (result.failed || 0)}, push: ${result.push_sent || 0}`;
    if (status) status.textContent = message;
    showToast("Рассылка отправлена");
    event.currentTarget.reset();
    event.currentTarget.elements.title.value = "JutsoVPN";
    event.currentTarget.elements.telegram.checked = true;
    event.currentTarget.elements.push.checked = true;
  } catch (error) {
    if (status) status.textContent = error.message || "Ошибка рассылки";
    showToast(error.message || "Не удалось отправить");
  }
}

function renderTabAnimations() {
  ensureLottieAnimation("connect", "connectBtnEmoji", "/static/emoji_525833635464.json", {
    renderer: "svg",
    loop: false,
    autoplay: false,
    speed: 0.9,
  });
  ensureLottieAnimation("copy", "copyBtnEmoji", "/static/sticker-5-copy.json?v=20260428", {
    renderer: "svg",
    loop: false,
    autoplay: false,
    speed: 0.9,
  });
  ensureLottieAnimation("settings", "settingsBtnEmoji", "/static/sticker (8).json?v=20260428", {
    renderer: "svg",
    loop: false,
    autoplay: false,
    speed: 0.9,
  });

  // Keep icons visible in idle state even after full re-renders.
  ["copy", "connect", "settings"].forEach((key) => {
    stopAnimationAtFrame(state.animations[key], 1);
  });
}

function renderCollapseAnimations() {
  ensureLottieAnimation("balanceCollapse", "balanceCollapseEmoji", COLLAPSE_EMOJI_PATH, {
    renderer: "svg",
    loop: false,
    autoplay: false,
    speed: state.prefersReducedMotion ? 0.7 : 0.95,
  });
  ensureLottieAnimation("purchaseCollapse", "purchaseCollapseEmoji", COLLAPSE_EMOJI_PATH, {
    renderer: "svg",
    loop: false,
    autoplay: false,
    speed: state.prefersReducedMotion ? 0.7 : 0.95,
  });
}

function renderAll() {
  syncBotWebAppChrome();
  renderHero();
  renderDevices();
  renderTariffs();
  renderDevicePurchaseCard();
  renderBalanceProviders();
  syncPendingPaymentButtons();
  renderAdmin();
  renderTabAnimations();
  renderCollapseAnimations();
  $("balanceToggle")?.classList.toggle("is-open", state.balanceCollapseOpen);
  syncCollapseState($("purchaseCollapseBody"), state.purchaseCollapseOpen);
  syncCollapseState($("balanceCollapseBody"), state.balanceCollapseOpen);
  bindInlinePurchaseEvents();
  syncAccessState();
  renderTour();
  renderSettingsPanel();
  syncBotWebAppChrome();
}

async function handlePaymentResult(result, fallbackMessage, checkTarget = "purchase") {
  if (result.payment_url) {
    if (checkTarget === "balance") {
      state.balanceCheckVisible = true;
    } else {
      state.purchaseCheckVisible = true;
    }
    state.purchaseStartedAt = Date.now();
    startCountdownTimer();
    const tg = window.Telegram?.WebApp;
    if (tg?.openLink) tg.openLink(result.payment_url);
    else window.open(result.payment_url, "_blank", "noopener");
    state.purchaseStatus = "Ссылка на оплату открыта. После оплаты данные обновятся автоматически.";
  } else {
    state.purchaseStatus = localizeMessage(result.message || fallbackMessage);
  }

  if (result.dashboard) {
    state.pendingDeviceDelete = null;
    applyDashboardUpdate(result.dashboard, state.session, { force: true });
  }

  if (!result.dashboard) renderAll();
  bumpLiveRefresh();
  const success = successModalFromPurchase(result, fallbackMessage, checkTarget);
  if (success) {
    resetPurchaseUiAfterSuccess();
    renderAll();
    showSuccessModal(success.title, success.text);
  }
  showToast(result.message || fallbackMessage);
}

async function submitExpandedPurchase(provider = state.purchaseProvider) {
  if (!state.expandedPurchase) return;
  if (!provider) {
    state.purchaseStatus = "Выберите способ оплаты.";
    renderTariffs();
    renderDevicePurchaseCard();
    bindInlinePurchaseEvents();
    return;
  }

  const payload = { provider };
  if (state.expandedPurchase.kind === "tariff") {
    payload.kind = "tariff";
    payload.tariff_key = state.expandedPurchase.tariffKey;
  }
  if (state.expandedPurchase.kind === "devices") {
    payload.kind = "devices";
    payload.count = Number(state.expandedPurchase.count || 1);
  }

  try {
    const result = await request("/api/payment", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await handlePaymentResult(result, "Платеж создан", "purchase");
  } catch (error) {
    showToast(error.message);
  }
}

function bindPurchaseMethodEvents() {
  document.querySelectorAll(".purchase-provider-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.purchaseProvider = button.dataset.provider || "";
      updatePaymentMethodLabels(document.querySelectorAll(".purchase-provider-button"), button);
      const payButton = $("purchasePayButton");
      if (payButton) payButton.disabled = !state.purchaseProvider;
      state.purchaseStatus = "";
      const status = $("purchaseStatus");
      if (status) status.textContent = "Способ оплаты выбран. Нажмите оплатить.";
    });
  });

  $("purchasePayButton")?.addEventListener("click", () => submitExpandedPurchase());
}

async function checkPayments() {
  try {
    const result = await request("/api/payment/check", {
      method: "POST",
      body: "{}",
    });
    state.pendingDeviceDelete = null;
    state.purchaseStatus = result.processed ? `Обработано оплат: ${result.processed}` : "Новых оплат пока нет";
    if (!result.dashboard?.meta?.has_pending_payments) {
      state.purchaseCheckVisible = false;
      state.balanceCheckVisible = false;
      state.giftCheckVisible = false;
    }
    applyDashboardUpdate(result.dashboard, state.session, { force: true });
    bumpLiveRefresh(result.processed ? 30000 : LIVE_FAST_WINDOW_MS);
    const success = successModalFromPaymentDetails(result.processed_details);
    if (success) {
      resetPurchaseUiAfterSuccess();
      renderAll();
      showSuccessModal(success.title, success.text);
    }
    showToast(state.purchaseStatus);
  } catch (error) {
    showToast(error.message);
  }
}

function bindInlinePurchaseEvents() {
  renderCollapseAnimations();

  $("purchaseCollapseToggle")?.addEventListener("click", () => {
    state.purchaseCollapseOpen = !state.purchaseCollapseOpen;
    playAnimationOnce(state.animations.purchaseCollapse);
    $("purchaseCollapseToggle")?.classList.toggle("is-open", state.purchaseCollapseOpen);
    animateCollapse($("purchaseCollapseBody"), state.purchaseCollapseOpen);
  });

  $("purchaseCheckButton")?.addEventListener("click", checkPayments);

  bindPurchaseMethodEvents();

  document.querySelectorAll(".purchase-close-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.expandedPurchase = null;
      state.purchaseProvider = "";
      state.purchaseCollapseOpen = false;
      state.purchaseCheckVisible = false;
      state.purchaseStartedAt = 0;
      state.purchaseStatus = "";
      stopCountdownTimer();
      renderTariffs();
      renderDevicePurchaseCard();
    });
  });
}

function startCountdownTimer() {
  stopCountdownTimer();
  state.countdownTimer = setInterval(() => {
    const countdownNode = $("purchaseCountdown");
    if (countdownNode) countdownNode.textContent = currentPurchaseCountdown();
    if (Date.now() - state.purchaseStartedAt >= PAYMENT_TTL_MS) {
      state.purchaseStatus = "Время ожидания истекло. Создайте новый платеж.";
      stopCountdownTimer();
      renderTariffs();
      renderDevicePurchaseCard();
      bindInlinePurchaseEvents();
    }
  }, 1000);
}

function stopCountdownTimer() {
  if (!state.countdownTimer) return;
  clearInterval(state.countdownTimer);
  state.countdownTimer = null;
}

async function refreshDashboardSilently() {
  if (state.liveRefreshInFlight || document.hidden) return;
  state.liveRefreshInFlight = true;
  $("liveBadge")?.classList.add("is-syncing");

  try {
    const now = Date.now();
    const shouldCheckPayments = hasPendingPaymentWatch() && now - state.liveRefreshLastPaymentCheck >= LIVE_PAYMENT_CHECK_MS;
    const sessionData = shouldCheckPayments
      ? await request("/api/payment/check", { method: "POST", body: "{}" })
      : await request("/api/session");

    if (shouldCheckPayments) {
      state.liveRefreshLastPaymentCheck = now;
      if (!sessionData.dashboard?.meta?.has_pending_payments) {
        state.purchaseCheckVisible = false;
        state.balanceCheckVisible = false;
      }
      if (Number(sessionData.processed || 0) > 0) {
        state.purchaseStatus = `Обработано оплат: ${sessionData.processed}`;
        const success = successModalFromPaymentDetails(sessionData.processed_details);
        if (success) {
          resetPurchaseUiAfterSuccess();
          renderAll();
          showSuccessModal(success.title, success.text);
        }
        showToast(state.purchaseStatus);
      }
    }

    if (!sessionData?.dashboard) return;
    if (now - state.liveRefreshLastConfigCheck >= 30000) {
      const nextConfig = await request("/api/config");
      const prevTariffs = JSON.stringify(state.config?.tariffs || []);
      const nextTariffs = JSON.stringify(nextConfig?.tariffs || []);
      state.config = nextConfig;
      state.liveRefreshLastConfigCheck = now;
      if (prevTariffs !== nextTariffs) {
        state.expandedPurchase = null;
        state.purchaseProvider = "";
        state.purchaseCollapseOpen = false;
        showToast("Цены обновлены");
      }
    }
    applyDashboardUpdate(sessionData.dashboard, sessionData.authenticated ? sessionData.session : state.session);
    showSuccessFromEvents(sessionData.success_events);
    if (!isTelegramWebApp() && Array.isArray(sessionData.notifications) && sessionData.notifications.length) {
      showNotificationSheet(sessionData.notifications);
    }
    state.liveRefreshErrorCount = 0;
  } catch (error) {
    state.liveRefreshErrorCount += 1;
    console.warn("live refresh failed", error);
  } finally {
    state.liveRefreshInFlight = false;
    $("liveBadge")?.classList.remove("is-syncing");
  }
}

function getLiveRefreshInterval() {
  const backoff = Math.min(state.liveRefreshErrorCount * 1000, 7000);
  return (hasFastLiveWindow() ? LIVE_REFRESH_PENDING_MS : LIVE_REFRESH_MS) + backoff;
}

function bumpLiveRefresh(duration = LIVE_FAST_WINDOW_MS) {
  state.liveRefreshFastUntil = Math.max(state.liveRefreshFastUntil, Date.now() + duration);
  if (!document.hidden) {
    stopLiveRefresh();
    state.liveRefreshTimer = window.setTimeout(liveRefreshTick, 600);
  }
}

async function liveRefreshTick() {
  await refreshDashboardSilently();
  if (!document.hidden) startLiveRefresh();
}

function startLiveRefresh() {
  stopLiveRefresh();
  if (document.hidden) return;
  state.liveRefreshTimer = window.setTimeout(liveRefreshTick, getLiveRefreshInterval());
}

function stopLiveRefresh() {
  if (!state.liveRefreshTimer) return;
  clearTimeout(state.liveRefreshTimer);
  state.liveRefreshTimer = null;
}

async function hydrate() {
  state.config = await request("/api/config");
  await ensureTelegramWebAppSession();
  const sessionData = await request("/api/session");
  state.session = sessionData.authenticated ? sessionData.session : null;

  // Strict Mini-App-only gate: if the page was NOT opened from inside Telegram
  // WebApp, never reveal the dashboard. Show the "Open via the bot" screen and
  // hide the entire app shell.
  if (!isTelegramWebApp() || !state.session) {
    state.dashboard = null;
    setBrowserAuthGate(true);
    installTelegramLoginWidget();
    return;
  }

  setBrowserAuthGate(false);
  logEvent("page_view", "miniapp_open", { lang: state.prefs?.lang, currency: state.prefs?.currency });
  const dashboard = sessionData.dashboard || {
    profile: {},
    subscription: {},
    devices: [],
    balance: { amount: 0 },
  };
  state.pendingDeviceDelete = null;

  applyDashboardUpdate(dashboard, state.session, { force: true, highlight: false });
  switchTab(state.activeTab);
  showSuccessFromEvents(sessionData.success_events);
  if (!isTelegramWebApp() && Array.isArray(sessionData.notifications) && sessionData.notifications.length) {
    showNotificationSheet(sessionData.notifications);
  }
  await claimGiftFromUrl();
  await refreshPushState();
  startFirstRunTourIfNeeded();
  if (!state.tourActive) maybeShowPushPrompt();
}

// =============================================================
// Preferences (language + currency) and Telegram Stars payments
// =============================================================
const PREFS_KEY = "sendvpn:prefs";
const PREFS_DEFAULT = { lang: "ru", currency: "rub", set: false };
const DASHBOARD_CACHE_KEY = "sendvpn:dashboard-cache";

function loadCachedDashboard() {
  try {
    const raw = window.localStorage?.getItem(DASHBOARD_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveCachedDashboard(payload) {
  try {
    if (!payload || typeof payload !== "object") {
      window.localStorage?.removeItem(DASHBOARD_CACHE_KEY);
      return;
    }
    window.localStorage?.setItem(DASHBOARD_CACHE_KEY, JSON.stringify(payload));
  } catch {}
}

function clearCachedDashboard() {
  try {
    window.localStorage?.removeItem(DASHBOARD_CACHE_KEY);
  } catch {}
}
const I18N = {
  ru: {
    apply: "Применить",
    promo_title: "Активировать промокод",
    promo_subtitle: "Введите код, бонус применяется сразу",
    stars_title: "Оплата Telegram Stars",
    stars_subtitle: "Купите ⭐ через Telegram — баланс пополнится автоматически",
    stars_pack_amount: "{n} ⭐",
    stars_pay_busy: "Открываем платёж в Telegram…",
    stars_pay_failed: "Не удалось создать платёж",
    stars_pay_success: "Оплата успешна — баланс пополнится в течение нескольких секунд",
    stars_open_telegram: "Откройте платёжку в Telegram",
    prefs_title: "Язык и валюта",
    prefs_subtitle: "Выберите язык интерфейса и валюту цен.",
    prefs_currency_title: "Валюта",
    prefs_currency_subtitle: "Выберите валюту, в которой показываются цены.",
    prefs_language: "Язык",
    prefs_currency: "Валюта",
    days_left: "дней осталось",
    home_title: "Главная",
    profile_title: "Профиль",
    finance_title: "Оплата",
    buy_title: "Купить",
    devices_title: "Устройства",
    welcome_title: "Добро пожаловать!",
    welcome_lead: "Выберите язык и валюту — это можно изменить в настройках в любой момент.",
    continue: "Продолжить · Continue",
    // hero / home
    hero_caption: "Дней осталось",
    hero_no_sub: "нет активной подписки",
    connect_oneclick: "Подключить в 1 клик",
    copy_link: "Скопировать ссылку",
    traffic: "Трафик",
    empty_yet: "Пока пусто",
    tap_to_connect: "Нажмите, чтобы подключиться",
    // buy
    tariff_label: "Тариф",
    days_n: "{n} дней",
    devices_n: "{n} устройств",
    sale: "Акция",
    buy: "Купить",
    gift: "Подарить",
    // finance
    balance: "Баланс",
    topup_title: "Пополнить баланс",
    topup_subtitle: "Выберите сумму и удобный способ оплаты",
    topup_hint: "Баланс можно пополнить от 10 ₽",
    payment_methods: "Способы оплаты",
    topup_pay: "Пополнить",
    check_payment: "Проверить оплату",
    // profile
    sub_link: "Ссылка подписки",
    sub_link_pending: "Ключ пока не выдан",
    status: "Статус",
    expires: "Истекает",
    telegram_id: "Telegram ID",
    login: "Вход",
    referrals: "Рефералы",
    allow_notifications: "Разрешить уведомления",
    settings: "Настройки",
    support: "Поддержка",
    legal_privacy_policy: "Политика конфиденциальности",
    legal_user_agreement: "Пользовательское соглашение",
    logout: "Выйти",
    refresh_my_data: "Обновить мои данные",
    logout_all: "Выйти со всех устройств",
    // trial
    trial_title: "Получить 3 дня бесплатной подписки",
    trial_channel: "Подпишитесь на канал",
    trial_channel_hint: "После подписки вернитесь сюда и нажмите «Активировать».",
    open_channel: "Открыть канал",
    trial_claim: "Получить",
    // auth gate
    auth_title: "Откройте через бота",
    auth_lead: "Личный кабинет JUTSOVPN работает только внутри Telegram Mini App. Откройте бота — он привяжет ваш профиль и синхронизирует подписку, баланс и устройства автоматически.",
    auth_note: "Если вы уже в Telegram — нажмите /start у бота и кнопку «Открыть приложение».",
    open_bot: "Открыть бота",
    loading: "Подготавливаем ваш кабинет",
    // aria + placeholders
    aria_change_lang: "Сменить язык",
    aria_sub_status: "Статус подписки",
    aria_close: "Закрыть",
    placeholder_amount: "Сумма",
    placeholder_promo: "Введите код",
    placeholder_gift_recipient: "Telegram ID или @username",
    placeholder_gift_message: "Например: держи доступ, приятного просмотра",
    // payment methods
    method_select: "Выбрать",
    method_sbp: "СБП",
    method_card: "Карта",
    method_cryptobot: "CryptoBot",
    // device card
    device_extra: "Доп.",
    device_extra_name: "устройство",
    // push sheet
    push_kicker: "Уведомления",
    push_title: "Будьте в курсе",
    push_text: "Сайт сможет присылать уведомления о подарках, оплатах и окончании подписки.",
    push_allow: "Разрешить уведомления",
    push_later: "Позже",
    // notification sheet
    notif_title: "У вас непрочитанные сообщения",
    notif_mark_read: "Отметить прочитанным",
    // success sheet
    success_title: "Готово",
    success_text_default: "Операция выполнена успешно.",
    success_continue: "Продолжить",
    // referral sheet
    ref_kicker: "Реферальная программа",
    ref_title: "Приглашайте друзей",
    ref_lead: "Друг должен перейти по вашей ссылке, подписаться на канал и активировать бесплатный доступ.",
    ref_total: "Всего приглашено",
    ref_active: "Активных",
    ref_earned: "Начислено с покупок",
    ref_link: "Ваша ссылка",
    ref_share: "Поделиться ссылкой",
    ref_copy: "Скопировать",
    ref_trial_rule: "+{n} дня за активного друга",
    ref_purchase_rule: "{n}% с покупок реферала на баланс",
    // gift sheet
    gift_kicker: "Подарочная подписка",
    gift_title: "Подарить доступ",
    gift_lead: "Выберите получателя или оставьте поле пустым, чтобы получить ссылку.",
    gift_recipient: "Получатель",
    gift_recipient_hint: "Оставьте пустым, если нужна ссылка для друга.",
    gift_message: "Сообщение",
    gift_show_name: "Показать моё имя",
    gift_pay: "Оплатить подарок",
    gift_check: "Проверить оплату",
    gift_status_default: "После оплаты другу придёт уведомление или ссылка для активации.",
    // settings sheet
    settings_kicker: "Безопасность",
    settings_lead: "Управляйте сессией и синхронизацией данных Telegram.",
    settings_sessions: "Сессии и устройства",
    settings_sessions_hint: "Обновите профиль из Telegram или завершите все активные входы.",
    settings_status_default: "Здесь появится статус операции.",
    settings_currency_rub: "Рубли · ₽",
    settings_currency_usd: "Доллары · $",
    // tour
    tour_skip: "Пропустить",
    tour_next: "Дальше",
    tour_done: "Готово",
    tour_home_text: "Здесь видно подписку, трафик, ссылку подключения и список устройств.",
    tour_buy_text: "Здесь выбирают тариф и докупают дополнительные устройства.",
    tour_finance_text: "Здесь пополняют баланс, проверяют платежи и активируют промокоды.",
    tour_profile_text: "Здесь хранится ссылка подписки, статус доступа и кнопка поддержки.",
    // welcome modal
    prefs_currency_rub: "Рубли · ₽",
    prefs_currency_usd: "Доллары · $",
    prefs_lang_ru: "Русский",
    prefs_lang_en: "English",
  },
  en: {
    apply: "Apply",
    promo_title: "Activate promo code",
    promo_subtitle: "Enter the code — the bonus is applied instantly",
    stars_title: "Telegram Stars payment",
    stars_subtitle: "Buy ⭐ through Telegram — your balance is topped up automatically",
    stars_pack_amount: "{n} ⭐",
    stars_pay_busy: "Opening Telegram checkout…",
    stars_pay_failed: "Failed to create payment",
    stars_pay_success: "Payment successful — balance will arrive within a few seconds",
    stars_open_telegram: "Open the checkout in Telegram",
    prefs_title: "Language & currency",
    prefs_subtitle: "Pick the UI language and price currency.",
    prefs_currency_title: "Currency",
    prefs_currency_subtitle: "Choose the currency used for prices.",
    prefs_language: "Language",
    prefs_currency: "Currency",
    days_left: "days left",
    home_title: "Home",
    profile_title: "Profile",
    finance_title: "Payment",
    buy_title: "Buy",
    devices_title: "Devices",
    welcome_title: "Welcome!",
    welcome_lead: "Choose your language and currency — you can change this in settings anytime.",
    continue: "Continue · Продолжить",
    hero_caption: "days left",
    hero_no_sub: "no active subscription",
    connect_oneclick: "Connect in one tap",
    copy_link: "Copy link",
    traffic: "Traffic",
    empty_yet: "Nothing here yet",
    tap_to_connect: "Tap to connect",
    tariff_label: "Plan",
    days_n: "{n} days",
    devices_n: "{n} devices",
    sale: "Sale",
    buy: "Buy",
    gift: "Gift",
    balance: "Balance",
    topup_title: "Top up balance",
    topup_subtitle: "Pick an amount and a convenient payment method",
    topup_hint: "Top up your balance from ₽10",
    payment_methods: "Payment methods",
    topup_pay: "Top up",
    check_payment: "Check payment",
    sub_link: "Subscription link",
    sub_link_pending: "Key not issued yet",
    status: "Status",
    expires: "Expires",
    telegram_id: "Telegram ID",
    login: "Login",
    referrals: "Referrals",
    allow_notifications: "Allow notifications",
    settings: "Settings",
    support: "Support",
    legal_privacy_policy: "Privacy Policy",
    legal_user_agreement: "User Agreement",
    logout: "Sign out",
    refresh_my_data: "Refresh my data",
    logout_all: "Sign out everywhere",
    trial_title: "Get 3 days of free subscription",
    trial_channel: "Subscribe to the channel",
    trial_channel_hint: "After subscribing, come back and tap “Activate”.",
    open_channel: "Open channel",
    trial_claim: "Claim",
    auth_title: "Open via the bot",
    auth_lead: "The JUTSOVPN dashboard works only inside the Telegram Mini App. Open the bot — it will link your profile and sync your subscription, balance and devices automatically.",
    auth_note: "If you’re already in Telegram, send /start to the bot and tap “Open app”.",
    open_bot: "Open the bot",
    loading: "Preparing your dashboard",
    aria_change_lang: "Change language",
    aria_sub_status: "Subscription status",
    aria_close: "Close",
    placeholder_amount: "Amount",
    placeholder_promo: "Enter code",
    placeholder_gift_recipient: "Telegram ID or @username",
    placeholder_gift_message: "E.g.: enjoy your access",
    method_select: "Select",
    method_sbp: "SBP",
    method_card: "Card",
    method_cryptobot: "CryptoBot",
    device_extra: "Extra",
    device_extra_name: "device",
    push_kicker: "Notifications",
    push_title: "Stay in the loop",
    push_text: "We will let you know about gifts, payments and expiring subscriptions.",
    push_allow: "Allow notifications",
    push_later: "Later",
    notif_title: "You have unread messages",
    notif_mark_read: "Mark all read",
    success_title: "Done",
    success_text_default: "Operation completed successfully.",
    success_continue: "Continue",
    ref_kicker: "Referral program",
    ref_title: "Invite friends",
    ref_lead: "Your friend follows your link, subscribes to the channel and activates the free access.",
    ref_total: "Invited total",
    ref_active: "Active",
    ref_earned: "Earned from purchases",
    ref_link: "Your link",
    ref_share: "Share link",
    ref_copy: "Copy",
    ref_trial_rule: "+{n} days per active friend",
    ref_purchase_rule: "{n}% of referral purchases to balance",
    gift_kicker: "Gift subscription",
    gift_title: "Gift access",
    gift_lead: "Pick a recipient or leave the field empty to get a sharable link.",
    gift_recipient: "Recipient",
    gift_recipient_hint: "Leave empty to get a shareable link.",
    gift_message: "Message",
    gift_show_name: "Show my name",
    gift_pay: "Pay for gift",
    gift_check: "Check payment",
    gift_status_default: "After payment your friend will get a notification or activation link.",
    settings_kicker: "Security",
    settings_lead: "Manage your session and Telegram sync.",
    settings_sessions: "Sessions and devices",
    settings_sessions_hint: "Refresh your profile from Telegram or sign out everywhere.",
    settings_status_default: "Operation status will appear here.",
    settings_currency_rub: "Roubles · ₽",
    settings_currency_usd: "Dollars · $",
    tour_skip: "Skip",
    tour_next: "Next",
    tour_done: "Done",
    tour_home_text: "Here you can see your subscription, traffic, the connection link and your devices.",
    tour_buy_text: "Here you choose a plan and buy extra device slots.",
    tour_finance_text: "Here you top up your balance, check payments and activate promo codes.",
    tour_profile_text: "Here is your subscription link, status and support button.",
    prefs_currency_rub: "Roubles · ₽",
    prefs_currency_usd: "Dollars · $",
    prefs_lang_ru: "Russian",
    prefs_lang_en: "English",
  },
};
const STARS_PACKS = [50, 100, 500, 1000, 2000];
const STARS_RATE_FALLBACK = { rub: 1.39, usd: 0.013 };

function loadPrefs() {
  try {
    const raw = window.localStorage?.getItem(PREFS_KEY);
    if (raw) return { ...PREFS_DEFAULT, ...JSON.parse(raw) };
  } catch {}
  return { ...PREFS_DEFAULT };
}

function savePrefs(prefs) {
  try {
    window.localStorage?.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {}
}

function getStarsRate(currency) {
  const cfg = state.config || {};
  if (currency === "usd") return Number(cfg.stars_rate_usd) || STARS_RATE_FALLBACK.usd;
  return Number(cfg.stars_rate_rub) || STARS_RATE_FALLBACK.rub;
}

function formatMoney(amount, currency) {
  const value = Number(amount) || 0;
  if (currency === "usd") return `$${value.toFixed(2)}`;
  return `${Math.round(value)} ₽`;
}

function t(key, params = {}) {
  const lang = (state.prefs && state.prefs.lang) || "ru";
  const map = I18N[lang] || I18N.ru;
  let str = map[key] ?? I18N.ru[key] ?? key;
  Object.keys(params).forEach((k) => {
    str = str.split(`{${k}}`).join(String(params[k]));
  });
  return str;
}

function applyTranslations(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (!key) return;
    const txt = t(key);
    if (txt) el.textContent = txt;
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (!key) return;
    const txt = t(key);
    if (txt) el.setAttribute("placeholder", txt);
  });
  root.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    const key = el.getAttribute("data-i18n-aria");
    if (!key) return;
    const txt = t(key);
    if (txt) el.setAttribute("aria-label", txt);
  });
  root.querySelectorAll("[data-i18n-html]").forEach((el) => {
    const key = el.getAttribute("data-i18n-html");
    if (!key) return;
    const txt = t(key);
    if (txt) el.innerHTML = txt;
  });
  // tabbar labels
  document.querySelectorAll(".tabbar-item").forEach((btn) => {
    const span = btn.querySelector("span:not(.tabbar-icon)");
    if (!span) return;
    const tab = btn.dataset.tab;
    const map = { home: "home_title", buy: "buy_title", finance: "finance_title", profile: "profile_title" };
    if (map[tab]) span.textContent = t(map[tab]);
  });
  // welcome modal
  const wt = document.getElementById("prefsTitle");
  if (wt) wt.textContent = t("welcome_title");
  const wl = document.querySelector("#prefsOverlay .referral-lead");
  if (wl) wl.textContent = t("welcome_lead");
  const wc = document.getElementById("prefsContinueButton");
  if (wc) wc.textContent = t("continue");
}

function highlightPrefsButtons(container, key, value) {
  container.querySelectorAll(`.prefs-buttons[data-prefs="${key}"] .prefs-btn`).forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.value === value);
  });
}

function setPref(key, value) {
  state.prefs = { ...state.prefs, [key]: value, set: true };
  savePrefs(state.prefs);
  document.querySelectorAll(".prefs-overlay, .settings-sheet").forEach((root) => {
    highlightPrefsButtons(root, key, value);
  });
  applyTranslations();
  renderStarsGrid();
  refreshFinanceBalanceDisplay();
}

function bindPrefsButtons() {
  document.querySelectorAll(".prefs-buttons").forEach((group) => {
    const key = group.dataset.prefs;
    if (!key) return;
    group.querySelectorAll(".prefs-btn").forEach((btn) => {
      btn.addEventListener("click", () => setPref(key, btn.dataset.value));
    });
  });
}

function refreshFinanceBalanceDisplay() {
  const balance = Number(state.dashboard?.balance?.amount || 0);
  const el = document.getElementById("financeBalanceValue");
  if (el) {
    if (state.prefs?.currency === "usd") {
      const usd = balance * (Number(state.config?.usd_rate_rub) || 0.011);
      el.textContent = `$${usd.toFixed(2)}`;
    } else {
      el.textContent = `${Math.round(balance)} ₽`;
    }
  }
}

function showPrefsOverlay() {
  const overlay = document.getElementById("prefsOverlay");
  if (!overlay) return;
  overlay.classList.remove("hidden");
  const cur = state.prefs || { ...PREFS_DEFAULT };
  highlightPrefsButtons(overlay, "lang", cur.lang);
  highlightPrefsButtons(overlay, "currency", cur.currency);
}

function hidePrefsOverlay() {
  const overlay = document.getElementById("prefsOverlay");
  if (!overlay) return;
  overlay.classList.add("hidden");
  state.prefs = { ...state.prefs, set: true };
  savePrefs(state.prefs);
}

function maybeShowPrefsOverlay() {
  // Disabled: language/currency selection moved to header toggle + profile settings.
  state.prefs = { ...state.prefs, set: true };
  savePrefs(state.prefs);
}

function applyHeaderLangToggle() {
  const node = document.getElementById("langToggleCurrent");
  if (!node) return;
  const lang = state.prefs?.lang || "ru";
  node.textContent = lang === "ru" ? "RU" : "EN";
}

function toggleHeaderLanguage() {
  const current = state.prefs?.lang || "ru";
  const next = current === "ru" ? "en" : "ru";
  logEvent("lang_toggle", `${current}→${next}`);
  state.prefs = { ...state.prefs, lang: next, set: true };
  savePrefs(state.prefs);
  // Smooth transition: fade body briefly while we re-render.
  document.body.classList.add("lang-switching");
  setTimeout(() => {
    applyTranslations();
    applyHeaderLangToggle();
    try { if (typeof renderTariffs === "function") renderTariffs(); } catch {}
    try { if (typeof renderStarsGrid === "function") renderStarsGrid(); } catch {}
    try { if (typeof renderDevices === "function") renderDevices(); } catch {}
    try { if (typeof applyDashboardUpdate === "function" && state.dashboard) applyDashboardUpdate(state.dashboard, state.session, { force: true, highlight: false }); } catch {}
    requestAnimationFrame(() => document.body.classList.remove("lang-switching"));
  }, 80);
}

function renderStarsGrid() {
  const grid = document.getElementById("starsGrid");
  if (!grid) return;
  const currency = state.prefs?.currency || "rub";
  const rate = getStarsRate(currency);
  grid.innerHTML = STARS_PACKS.map((amount) => {
    const total = amount * rate;
    const price = formatMoney(total, currency);
    return `
      <button class="star-pack" type="button" data-stars="${amount}">
        <span class="star-pack-amount">${amount}</span>
        <span class="star-pack-price">≈ ${price}</span>
      </button>
    `;
  }).join("");
  grid.querySelectorAll(".star-pack").forEach((btn) => {
    btn.addEventListener("click", () => payWithStars(Number(btn.dataset.stars), btn));
  });
}

async function payWithStars(amount, button) {
  const status = document.getElementById("starsStatus");
  if (button) button.dataset.busy = "true";
  if (status) status.textContent = t("stars_pay_busy");
  try {
    const result = await request("/api/payment/stars/create-invoice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stars: amount, currency: state.prefs?.currency || "rub" }),
    });
    if (!result.ok || !result.invoice_link) {
      throw new Error(result.error || t("stars_pay_failed"));
    }
    const tg = window.Telegram?.WebApp;
    if (tg?.openInvoice) {
      tg.openInvoice(result.invoice_link, (status_) => {
        if (status_ === "paid") {
          if (status) status.textContent = t("stars_pay_success");
          bumpLiveRefresh(60000);
        } else if (status_ === "failed") {
          if (status) status.textContent = t("stars_pay_failed");
        }
      });
    } else if (tg?.openLink) {
      tg.openLink(result.invoice_link);
      if (status) status.textContent = t("stars_open_telegram");
    } else {
      window.open(result.invoice_link, "_blank");
      if (status) status.textContent = t("stars_open_telegram");
    }
  } catch (error) {
    if (status) status.textContent = error?.message || t("stars_pay_failed");
  } finally {
    if (button) button.dataset.busy = "false";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  state.prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches || false;
  if (window.lottie?.setQuality) window.lottie.setQuality("medium");
  if (window.lottie?.setSubframe) window.lottie.setSubframe(false);

  state.prefs = loadPrefs();
  state.prefs.set = true; // first-run modal disabled — defaults applied immediately.
  savePrefs(state.prefs);
  bindPrefsButtons();
  applyTranslations();
  applyHeaderLangToggle();
  renderStarsGrid();
  document.getElementById("langToggle")?.addEventListener("click", () => {
    toggleHeaderLanguage();
  });

  // Profile -> "Ссылка подписки / Ключ пока не выдан" delegated handler.
  // When the user taps the placeholder link (rendered into #profileKey
  // when no sub_url is issued yet), open the /sub page through the
  // Telegram WebApp so it stays inside the chat.
  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target.closest("[data-sub-page-link='true']") : null;
    if (!target) return;
    event.preventDefault();
    const href = target.getAttribute("href") || (state.config?.sub_page_url || "/sub");
    const url = /^https?:\/\//i.test(href) ? href : new URL(href, location.origin).toString();
    if (!openExternalLink(url)) {
      window.open(url, "_blank", "noopener");
    }
  });

  // Strict Mini-App-only gate: if we're in a regular browser, show the auth
  // screen immediately so the dashboard never flashes.
  if (!isTelegramWebApp()) {
    setBrowserAuthGate(true);
    installTelegramLoginWidget();
    return;
  }

  openWebAppFullscreen();
  startLoadingScreen();

  // Pre-paint the dashboard from localStorage cache so the hero ("до DD
  // месяца YYYY") and profile (sub_url link) are visible immediately on
  // revisit, before /api/session resolves. The shell stays hidden behind
  // the loading screen until hydrate() finishes; this just guarantees the
  // values are correct the moment the screen appears.
  try {
    const cached = loadCachedDashboard();
    if (cached?.dashboard) {
      applyDashboardUpdate(cached.dashboard, cached.session || state.session, { force: true, highlight: false });
    }
  } catch {}

  try {
    await hydrate();
  } catch (error) {
    showToast(error.message);
  } finally {
    await finishLoadingScreen();
  }

  startLiveRefresh();
  // Тур показывается только на первом заходе (флаг живёт в localStorage).
  setTimeout(() => startFirstRunTourIfNeeded(false), 240);
  // Окошко выбора языка/валюты — показываем при первом заходе.
  setTimeout(maybeShowPrefsOverlay, 600);
  applyTranslations();
  renderStarsGrid();
  refreshFinanceBalanceDisplay();

  // Desktop hardening: block copy/select/context menu/saving shortcuts.
  if (!isTelegramWebApp() && window.matchMedia?.("(pointer: fine)")?.matches) {
    const block = (event) => event.preventDefault();
    ["contextmenu", "copy", "cut", "selectstart", "dragstart"].forEach((eventName) => {
      document.addEventListener(eventName, block);
    });
    document.addEventListener("keydown", (event) => {
      const key = String(event.key || "").toLowerCase();
      const ctrlOrMeta = event.ctrlKey || event.metaKey;
      if (
        (ctrlOrMeta && ["c", "x", "s", "u"].includes(key)) ||
        (event.ctrlKey && event.shiftKey && ["i", "j", "c"].includes(key)) ||
        key === "f12"
      ) {
        event.preventDefault();
      }
    });
  }

  document.querySelectorAll(".tabbar-item").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });

  $("trialClaimButton")?.addEventListener("click", claimFreeTrial);
  $("trialChannelButton")?.addEventListener("click", () => {
    if (!openExternalLink(getChannelUrl())) showToast("Ссылка канала недоступна");
  });
  $("tourSkipButton")?.addEventListener("click", finishTour);
  $("tourNextButton")?.addEventListener("click", nextTourStep);
  $("successContinueButton")?.addEventListener("click", hideSuccessModal);

  $("copyButton").addEventListener("click", async () => {
    playAnimationOnce(state.animations.copy);
    const text = state.dashboard?.subscription?.sub_url || "";
    if (!text) {
      showToast("Ключ еще не выдан");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      showToast("Ссылка скопирована");
    } catch {
      showToast("Не удалось скопировать");
    }
  });

  $("connectButton").addEventListener("click", () => {
    playAnimationOnce(state.animations.connect);
    const link = firstSubscriptionLink(state.dashboard?.subscription?.sub_url);
    if (!link || !canOpenDirectLink(link)) {
      showToast("Нет ссылки для подключения");
      return;
    }
    bumpLiveRefresh(120000);
    const tg = window.Telegram?.WebApp;
    if (tg?.openLink && /^https?:\/\//i.test(link)) {
      tg.openLink(link);
      return;
    }
    window.location.href = link;
  });

  $("referralsButton")?.addEventListener("click", showReferralSheet);
  $("pushPermissionButton")?.addEventListener("click", enablePushNotifications);
  $("settingsButton")?.addEventListener("click", () => {
    playAnimationOnce(state.animations.settings);
    openSettingsSheet();
  });
  $("settingsCloseButton")?.addEventListener("click", closeSettingsSheet);
  $("settingsSheet")?.addEventListener("click", (event) => {
    if (event.target === event.currentTarget) closeSettingsSheet();
  });
  $("refreshProfileButton")?.addEventListener("click", refreshProfileFromTelegram);
  $("logoutAllButton")?.addEventListener("click", logoutAllSessions);
  $("pushEnableButton")?.addEventListener("click", enablePushNotifications);
  $("pushLaterButton")?.addEventListener("click", () => {
    hidePushPrompt();
    try {
      window.localStorage?.setItem(pushStorageKey(), "done");
    } catch {
      // ignore storage restrictions
    }
  });
  $("notificationCloseButton")?.addEventListener("click", hideNotificationSheet);
  $("notificationReadAllButton")?.addEventListener("click", dismissNotifications);
  $("notificationSheet")?.addEventListener("click", (event) => {
    if (event.target === event.currentTarget) hideNotificationSheet();
  });
  $("adminBroadcastForm")?.addEventListener("submit", submitAdminBroadcast);
  $("logoutButton")?.addEventListener("click", logout);
  $("referralCloseButton")?.addEventListener("click", hideReferralSheet);
  $("referralSheet")?.addEventListener("click", (event) => {
    if (event.target === event.currentTarget) hideReferralSheet();
  });
  $("referralCopyButton")?.addEventListener("click", async () => {
    const link = String(state.dashboard?.referrals?.link || "").trim();
    if (!link) {
      showToast("Реферальная ссылка пока недоступна");
      return;
    }
    try {
      await navigator.clipboard.writeText(link);
      showToast("Реферальная ссылка скопирована");
    } catch {
      showToast("Не удалось скопировать");
    }
  });
  $("referralShareButton")?.addEventListener("click", shareReferralLink);
  $("giftCloseButton")?.addEventListener("click", hideGiftSheet);
  $("giftSheet")?.addEventListener("click", (event) => {
    if (event.target === event.currentTarget) hideGiftSheet();
  });
  $("giftPayButton")?.addEventListener("click", submitGiftPayment);
  $("giftCheckPaymentsButton")?.addEventListener("click", checkPayments);
  $("giftRecipientInput")?.addEventListener("input", scheduleGiftRecipientLookup);
  $("giftShowSenderInput")?.addEventListener("change", renderGiftSheet);
  // Balance payment method selection (static demo providers)
  document.querySelectorAll('#balanceProviderList .payment-method').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('#balanceProviderList .payment-method').forEach((b) => b.classList.remove('is-selected'));
      button.classList.add('is-selected');
      document.querySelectorAll('#balanceProviderList .payment-method .payment-method-meta').forEach((m) => m.textContent = 'Выбрать');
      const meta = button.querySelector('.payment-method-meta');
      if (meta) meta.textContent = 'Выбран';
      const pay = $('balancePayButton');
      if (pay) pay.disabled = false;
    });
  });

  // Make static plan cards clickable: if config lacks tariffs, create temporary entries
  function ensureTariffFromDom(key, node) {
    if (!key) return null;
    if (!state.config) state.config = {};
    if (!Array.isArray(state.config.tariffs)) state.config.tariffs = [];
    if (getTariffByKey(key)) return getTariffByKey(key);

    const parseCard = (card) => {
      if (!card) return null;
      const keyNode = card.querySelector('[data-tariff]');
      const cardKey = keyNode?.dataset?.tariff;
      if (!cardKey) return null;
      const nameNode = card.querySelector('.plan-name');
      const priceNode = card.querySelector('.plan-price, .new-price');
      const metaNode = card.querySelector('.plan-meta');
      const name = nameNode ? nameNode.textContent.trim() : cardKey;
      const priceText = priceNode ? priceNode.textContent.trim() : '';
      const priceMatch = priceText.replace(/\s+/g, '').match(/(\d+)/);
      const price = priceMatch ? Number(priceMatch[1]) : 0;
      let days = 0;
      let devices = 0;
      if (metaNode) {
        const parts = metaNode.textContent.split(/[·,]/).map((s) => s.trim());
        parts.forEach((part) => {
          const dayMatch = part.match(/(\d+)\s*д/);
          if (dayMatch) days = Number(dayMatch[1]);
          const deviceMatch = part.match(/(\d+)\s*у/);
          if (deviceMatch) devices = Number(deviceMatch[1]);
        });
      }
      return { key: cardKey, name, rub: price, days: days || 0, devices: devices || 0 };
    };

    // Seed all visible cards once, so closing a purchase does not collapse list to one tariff.
    const staticCards = Array.from(document.querySelectorAll('#tariffList .plan-card'));
    staticCards.forEach((card) => {
      const parsed = parseCard(card);
      if (!parsed || getTariffByKey(parsed.key)) return;
      state.config.tariffs.push(parsed);
    });

    if (getTariffByKey(key)) return getTariffByKey(key);

    // Fallback for a detached node not in #tariffList.
    const parsedCurrent = parseCard(node.closest('.plan-card'));
    if (parsedCurrent && !getTariffByKey(parsedCurrent.key)) {
      state.config.tariffs.push(parsedCurrent);
    }
    return getTariffByKey(key);
  }

  // attach handlers to static buttons (delegation)
  document.body.addEventListener('click', (ev) => {
    const buy = ev.target.closest('.cta.c cta-primary, .cta.c cta-primary, .cta.c cta-primary');
    // fallback: find by data-tariff on any button
    const btn = ev.target.closest('[data-tariff]');
    if (!btn) return;
    const key = btn.dataset.tariff;
    if (!key) return;
    const isGift = btn.classList.contains('cta-secondary') || btn.classList.contains('tariff-gift-button');
    const tariff = getTariffByKey(key) || ensureTariffFromDom(key, btn);
    if (!tariff) return;
    if (isGift) {
      showGiftSheet(tariff.key);
      return;
    }
    // ensure demo providers exist so payment methods show
    if (!state.config.providers || Object.keys(state.config.providers).length === 0) {
      state.config.providers = { sbp: true, card: true, crypto: true, balance: true };
    }
    state.expandedPurchase = { kind: 'tariff', tariffKey: tariff.key };
    state.purchaseProvider = '';
    state.purchaseCollapseOpen = false;
    state.purchaseCheckVisible = false;
    state.purchaseStartedAt = 0;
    state.purchaseStatus = '';
    renderTariffs();
    renderDevicePurchaseCard();
    bindInlinePurchaseEvents?.();
    btn.closest('.plan-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
  $("giftDeviceRange")?.addEventListener("input", (event) => {
    state.giftDeviceCount = Number(event.currentTarget.value || 1);
    state.giftProvider = "";
    renderGiftSheet();
  });

  $("supportButton").addEventListener("click", (event) => {
    const supportLink = state.config?.support_url || "https://t.me/jutsodev";
    const tg = window.Telegram?.WebApp;
    if (tg?.openTelegramLink && /^https?:\/\/t\.me\//i.test(supportLink)) {
      event.preventDefault();
      tg.openTelegramLink(supportLink);
      return;
    }
    if (tg?.openLink) {
      event.preventDefault();
      tg.openLink(supportLink);
    }
    // otherwise let the <a href> do its thing
  });

  const promoForm = $("promoForm");
  const promoInput = promoForm.querySelector('input[name="code"]');
  const promoButton = promoForm.querySelector('button[type="submit"]');
  const updatePromoButtonState = () => {
    const hasCode = promoInput.value.trim().length > 0;
    promoButton.classList.toggle("cta-primary", hasCode);
    promoButton.classList.toggle("cta-secondary", !hasCode);
  };

  promoInput.addEventListener("input", updatePromoButtonState);
  updatePromoButtonState();

  promoForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const result = await request("/api/promo", {
        method: "POST",
        body: JSON.stringify({ code: form.get("code") }),
      });
      applyDashboardUpdate(result.dashboard, state.session, { force: true });
      bumpLiveRefresh(30000);
      showSuccessModal("Успешная активация", result.message || "Промокод активирован.");
      showToast(result.message || "Промокод активирован");
      event.currentTarget.reset();
      updatePromoButtonState();
    } catch (error) {
      showToast(error.message);
    }
  });

  $("balanceToggle").addEventListener("click", () => {
    const body = $("balanceCollapseBody");
    const willOpen = !state.balanceCollapseOpen;
    state.balanceCollapseOpen = willOpen;
    playAnimationOnce(state.animations.balanceCollapse);
    animateCollapse(body, willOpen);
    $("balanceToggle").classList.toggle("is-open", willOpen);
  });

  document.querySelector('#balanceForm input[name="amount"]').addEventListener("input", renderBalanceProviders);

  $("balanceForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const provider = event.currentTarget.querySelector(".balance-provider-button.is-selected")?.dataset.provider;

    if (!provider) {
      showToast("Выберите способ оплаты");
      return;
    }

    try {
      const result = await request("/api/payment", {
        method: "POST",
        body: JSON.stringify({
          kind: "balance",
          amount: Number(form.get("amount")),
          provider,
        }),
      });
      await handlePaymentResult(result, "Ссылка на оплату готова", "balance");
    } catch (error) {
      showToast(error.message);
    }
  });

  $("balanceCheckPaymentsButton").addEventListener("click", checkPayments);

  window.addEventListener("error", (event) => {
    showToast(event.message || "Ошибка интерфейса");
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopLiveRefresh();
      return;
    }
    refreshDashboardSilently();
    startLiveRefresh();
  });

  window.addEventListener("focus", () => {
    refreshDashboardSilently();
    bumpLiveRefresh(30000);
  });
});
