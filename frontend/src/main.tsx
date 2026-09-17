import React, { startTransition, useDeferredValue, useEffect, useEffectEvent, useRef, useState } from "react";
import { createPortal } from "react-dom";
import ReactDOM from "react-dom/client";
import { AnimatePresence, motion, useDragControls } from "framer-motion";
import type { PanInfo } from "framer-motion";

import "./styles.css";
import { findMatchingStatementRuleForChoice, prioritizeStatementQuickChoices } from "./lib/statementClarification";
import { resolveStatementHistorySelection } from "./lib/statementSelection";

type Language = "ru" | "kk" | "en" | "uk";
type TabId = "map" | "cashier" | "quick" | "sandbox" | "settings";
type DeepLinkFocus = "clarify" | "statement";
type WorkspaceRole = "owner" | "cfo" | "coo" | "cashier" | "family_member";

type ActorContext = {
  telegramUserId: number | null;
  telegramChatId: number | null;
  workspaceRole: WorkspaceRole;
};

type DashboardMacro = {
  as_of: string;
  total_balance: string;
  business_balance: string;
  personal_balance: string;
  monthly_income: string;
  monthly_expense: string;
  account_balances: Array<{ account_type: string; label: string; balance: string }>;
  bridge_totals: Array<{ slug: string; label: string; amount: string; transaction_count: number }>;
  imported_statements_total: number;
  clarification_open_total: number;
};

type ProjectionPoint = {
  date: string;
  opening_balance: string;
  inflow: string;
  outflow: string;
  closing_balance: string;
};

type SafeToWithdraw = {
  safe_amount: string;
  reserve_buffer: string;
  projected_gap_date: string | null;
  available_business_balance: string;
  upcoming_obligations_total: string;
};

type GapScenario = {
  order: number;
  title: string;
  action: string;
  urgency: string;
  estimated_impact: string;
  reversible: boolean;
};

type InflationLeader = {
  sku_key: string;
  sku_name: string;
  category: string;
  latest_price: string;
  previous_price: string | null;
  price_change_pct: string | null;
  latest_seen_at: string;
  merchant_name: string | null;
};

type ReceiptItem = {
  sku_name: string;
  category: string;
  quantity: string;
  unit_price: string;
  total_price: string;
};

type ReceiptSummary = {
  id: number;
  merchant_name: string | null;
  currency: string;
  total_amount: string;
  purchased_at: string;
  parsed_status: string;
  items: ReceiptItem[];
};

type DashboardMedium = {
  as_of: string;
  safe_to_withdraw: SafeToWithdraw;
  projection: ProjectionPoint[];
  gap_scenarios: GapScenario[];
  obligations_total: string;
  recent_receipts_total: number;
  recent_receipts_amount: string;
  tracked_skus_total: number;
  inflation_leaders: InflationLeader[];
  last_receipt: ReceiptSummary | null;
  recent_transactions: Array<{
    id: number;
    account_name: string;
    account_type: string;
    transaction_type: string;
    category: string;
    amount: string;
    created_at: string;
    note: string | null;
  }>;
};

type ClarificationRulePreview = {
  match_key: string;
  account_type: string;
  life_sector: string;
  explanation: string;
};

type PendingClarification = {
  statement_id: number;
  parsed_count: number;
  auto_count: number;
  remaining_count: number;
  current_item: {
    index: number;
    statement_date: string;
    amount: string;
    transaction_type: string;
    counterparty: string;
    description: string;
    reason: string;
    suggested_account_type: string | null;
    suggested_life_sector: string | null;
    matched_rules: ClarificationRulePreview[];
  };
};

type DashboardMicro = {
  as_of: string;
  profile_name: string | null;
  preferred_language: string | null;
  onboarding_completed: boolean | null;
  pending_clarification: PendingClarification | null;
  recent_rules: Array<{
    match_key: string;
    account_type: string;
    life_sector: string;
    explanation: string;
  }>;
  last_import: {
    id: number;
    source_name: string;
    original_filename: string | null;
    imported_at: string;
    parse_status: string;
    note: string | null;
  } | null;
  webapp_url: string;
  quick_add_path: string;
};

type DashboardBundle = {
  macro: DashboardMacro;
  medium: DashboardMedium;
  micro: DashboardMicro;
};

type StatementImportResult = {
  imported_statement_id: number;
  parsed_count: number;
  auto_count: number;
  unclear_count: number;
  summary_message: string;
  prompt_message: string | null;
  pending: StatementPending | null;
  latest_status: StatementStatusSnapshot | null;
  history: StatementHistoryEntry[];
};

type StatementPendingItem = {
  index: number;
  statement_date: string;
  amount: string | number;
  transaction_type: string;
  counterparty: string;
  description: string;
  reason: string;
  suggested_account_type: string | null;
  suggested_life_sector: string | null;
  matched_rules: ClarificationRulePreview[];
};

type StatementPending = {
  statement_id: number;
  parsed_count: number;
  auto_count: number;
  current_index: number;
  total_count: number;
  resolved_count: number;
  remaining_count: number;
  prompt_message: string;
  current_item: StatementPendingItem | null;
  items: StatementPendingItem[];
};

type StatementStatusSnapshot = {
  imported_statement_id: number;
  source_name: string;
  original_filename: string | null;
  parse_status: string;
  imported_at: string;
  parsed_count: number | null;
  auto_count: number | null;
  unclear_count: number | null;
  remaining_clarifications: number;
};

type StatementWorkbenchStatus = {
  latest_status: StatementStatusSnapshot | null;
  pending: StatementPending | null;
};

type StatementHistoryEntry = {
  imported_statement_id: number;
  source_name: string;
  original_filename: string | null;
  parse_status: string;
  imported_at: string;
  parsed_count: number | null;
  auto_count: number | null;
  unclear_count: number | null;
  remaining_clarifications: number;
};

type StatementSourceTarget = {
  imported_statement_id: number;
  source_name: string;
  original_filename: string | null;
  storage_kind?: string;
  file_available?: boolean;
  raw_line_count?: number;
};

type StatementDetail = {
  imported_statement_id: number;
  source_name: string;
  original_filename: string | null;
  parse_status: string;
  imported_at: string;
  parsed_count: number | null;
  auto_count: number | null;
  unclear_count: number | null;
  remaining_clarifications: number;
  note: string | null;
  storage_kind: string;
  file_available: boolean;
  is_active: boolean;
  raw_line_count: number;
  raw_preview: string;
  raw_preview_truncated: boolean;
  pending: StatementPending | null;
};

type StatementWorkbenchResponse = {
  latest_status: StatementStatusSnapshot | null;
  pending: StatementPending | null;
  history: StatementHistoryEntry[];
};

type StatementClarificationResult = {
  message: string;
  pending: StatementPending | null;
  latest_status: StatementStatusSnapshot | null;
  history: StatementHistoryEntry[];
};

type StatementQuickChoice = {
  labels: Record<Language, string>;
  account_type: string;
  life_sector: string;
};

type QuickAddResult = {
  transaction: {
    id: number;
    amount: string;
    category: string;
    type: string;
    note: string | null;
    created_at: string;
  };
  account_type: string;
  route: string;
  normalized_text: string;
  message: string;
};

type QuickAssistantResult = {
  answer: string;
  total_amount: string;
  transaction_count: number;
  matched_categories: string[];
  period_start: string | null;
  period_end: string | null;
  route: string;
  source: string;
};

type ReceiptUploadResult = {
  message: string;
  receipt: ReceiptSummary | null;
};

type ProfilePreferenceResponse = {
  telegram_user_id: number;
  preferred_language: Language;
};

type HypothesisAgentRationale = {
  agent: string;
  stance: string;
  summary: string;
  signals: string[];
};

type HypothesisScorecard = {
  probability_of_success: string;
  verdict: string;
  runway_label: string;
  cash_pressure_pct: string;
  payback_days: number | null;
  projected_return_amount: string;
  net_return_amount: string;
  safe_corridor_remaining: string;
  baseline_gap_date: string | null;
  scenario_gap_date: string | null;
  max_delta_drawdown: string;
};

type HypothesisScoreResponse = {
  title: string;
  initiator_role: string;
  risk_level: string;
  scorecard: HypothesisScorecard;
  agents: HypothesisAgentRationale[];
  simulation: {
    title: string;
    role_perspective: string;
    risk_level: string;
    payback_date: string | null;
    baseline_curve: ProjectionPoint[];
    hypothesis_curve: ProjectionPoint[];
    delta_curve: ProjectionPoint[];
  };
};

type QuickCaptureCopy = {
  title: string;
  body: string;
  heroKicker: string;
  closeAction: string;
  placeholder: string;
  submit: string;
  submitBusy: string;
  loadIncome: string;
  loadExpense: string;
  accountTitle: string;
  accountBusiness: string;
  accountPersonal: string;
  previewHint: string;
  assistantTitle: string;
  samplesTitle: string;
  resultTitle: string;
  routeLabel: string;
  receiptTitle: string;
  receiptBody: string;
  receiptCta: string;
  receiptBusy: string;
  receiptHint: string;
  receiptReady: string;
};

type QuickCaptureExamples = {
  income: string;
  expense: string;
  alt: string;
};

type SandboxCopy = {
  lag: string;
  probability: string;
  verdict: string;
  liveRationaleTitle: string;
  liveRationaleBody: string;
  modelingBusy: string;
  runwayInside: string;
  runwayTight: string;
  runwayOutside: string;
  approve: string;
  stage: string;
  hold: string;
  noPreview: string;
  pressureDelta: string;
};

type MiniAppLanguageCopy = {
  names: Record<Language, string>;
  saved: string;
  previewSaved: string;
  saving: string;
  failed: string;
  settingsHint: string;
  profileLanguage: string;
  systemNotesTitle: string;
  systemNotesBody: string;
  apiLabel: string;
  userLabel: string;
  asOfLabel: string;
  browserPreview: string;
  fileLabel: string;
  receiptFallback: string;
  flowItems: string;
  leftLabel: string;
  paybackDays: string;
  projectionEmpty: string;
  parseStatus: Record<string, string>;
  agentStance: Record<string, string>;
  accountType: Record<string, string>;
};

type StatementWorkbenchCopy = {
  importTitle: string;
  importBody: string;
  draftPlaceholder: string;
  importAction: string;
  importBusy: string;
  uploadAction: string;
  uploadBusy: string;
  uploadHint: string;
  sampleAction: string;
  previewHint: string;
  activeUser: string;
  livePrompt: string;
  replyPlaceholder: string;
  sendReply: string;
  quickChoices: string;
  suggestedBadge: string;
  textReplyHint: string;
  importFirst: string;
  workbenchIdle: string;
  workbenchIdleBody: string;
  statusTitle: string;
  statusBody: string;
  refreshAction: string;
  importedLabel: string;
  parsedLabel: string;
  autoLabel: string;
  openLabel: string;
  historyTitle: string;
  historyBody: string;
  historyEmpty: string;
  historyResumeAction: string;
  historyResumeHint: string;
  historyResumeNotice: string;
  sourceDownloadAction: string;
  sourceDownloadBusy: string;
  sourceDownloaded: string;
  sampleLoaded: string;
  statusRefreshed: string;
};

type SettingsMarketCard = {
  title: string;
  body: string;
  badge: string;
  tone: "urgent" | "planned" | "support" | "watch";
};

type TelegramSafeAreaInset = {
  top?: number;
  right?: number;
  bottom?: number;
  left?: number;
};

type TelegramTheme = {
  bg_color?: string;
  secondary_bg_color?: string;
  text_color?: string;
  hint_color?: string;
  button_color?: string;
};

type TelegramHapticImpactStyle = "light" | "medium" | "heavy" | "rigid" | "soft";
type TelegramHapticNotificationType = "error" | "success" | "warning";

type TelegramBackButton = {
  isVisible?: boolean;
  show?: () => void;
  hide?: () => void;
  onClick?: (handler: () => void) => void;
  offClick?: (handler: () => void) => void;
};

type TelegramHapticFeedback = {
  impactOccurred?: (style: TelegramHapticImpactStyle) => void;
  notificationOccurred?: (type: TelegramHapticNotificationType) => void;
  selectionChanged?: () => void;
};

declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        ready: () => void;
        expand: () => void;
        requestFullscreen?: () => void;
        openTelegramLink?: (url: string) => void;
        openLink?: (url: string) => void;
        setHeaderColor?: (color: string) => void;
        setBackgroundColor?: (color: string) => void;
        setBottomBarColor?: (color: string) => void;
        enableVerticalSwipes?: () => void;
        disableVerticalSwipes?: () => void;
        enableClosingConfirmation?: () => void;
        disableClosingConfirmation?: () => void;
        onEvent?: (event: string, handler: (...args: unknown[]) => void) => void;
        offEvent?: (event: string, handler: (...args: unknown[]) => void) => void;
        BackButton?: TelegramBackButton;
        HapticFeedback?: TelegramHapticFeedback;
        safeAreaInset?: TelegramSafeAreaInset;
        contentSafeAreaInset?: TelegramSafeAreaInset;
        themeParams?: TelegramTheme;
        initDataUnsafe?: {
          user?: {
            id?: number;
            language_code?: string;
            first_name?: string;
          };
        };
      };
    };
  }
}

const LANGUAGE_STORAGE_KEY = "qaltam-miniapp-language";

const statementQuickChoices: StatementQuickChoice[] = [
  {
    labels: { ru: "Продажи / Доход", kk: "Сату / Кіріс", en: "Sales / Income", uk: "Продажі / Дохід" },
    account_type: "business",
    life_sector: "sales_income",
  },
  {
    labels: { ru: "Закуп / Товар", kk: "Қор / Тауар", en: "Inventory / Parts", uk: "Запаси / Товар" },
    account_type: "business",
    life_sector: "inventory_parts",
  },
  {
    labels: { ru: "Аренда / Коммуналка", kk: "Жалдау / Коммуналдық", en: "Rent / Utilities", uk: "Оренда / Комунальні" },
    account_type: "business",
    life_sector: "rent_utilities",
  },
  {
    labels: { ru: "Налоги / Комиссии", kk: "Салық / Комиссия", en: "Taxes / Fees", uk: "Податки / Комісії" },
    account_type: "business",
    life_sector: "taxes_fees",
  },
  {
    labels: { ru: "Семья / Быт", kk: "Отбасы / Тұрмыс", en: "Family / Living", uk: "Сім'я / Побут" },
    account_type: "personal",
    life_sector: "family_living",
  },
  {
    labels: { ru: "Сбережения / Долги", kk: "Жинақ / Қарыз", en: "Savings / Debt", uk: "Заощадження / Борги" },
    account_type: "personal",
    life_sector: "savings_debt",
  },
  {
    labels: { ru: "Вывод владельцу", kk: "Ие шығымы", en: "Owner Draw", uk: "Виведення власнику" },
    account_type: "personal",
    life_sector: "owner_draw",
  },
];

const miniAppLanguageCopy: Record<Language, MiniAppLanguageCopy> = {
  ru: {
    names: { ru: "Русский", kk: "Казахский", en: "English", uk: "Украинский" },
    saved: "Язык Mini App сохранен в профиле.",
    previewSaved: "Язык переключен на этом устройстве.",
    saving: "Сохраняю языковую настройку...",
    failed: "Не удалось сохранить язык профиля.",
    settingsHint: "Эта настройка синхронизирует язык Mini App и Telegram-ответов для вашего профиля.",
    profileLanguage: "Язык профиля",
    systemNotesTitle: "Системные заметки",
    systemNotesBody: "Локальная среда, actor headers и время последней сводки.",
    apiLabel: "API",
    userLabel: "Пользователь",
    asOfLabel: "Актуально на",
    browserPreview: "Детали импорта",
    fileLabel: "Файл",
    receiptFallback: "Чек",
    flowItems: "движений",
    leftLabel: "осталось",
    paybackDays: "Окупаемость",
    projectionEmpty: "График появится, когда накопится история транзакций.",
    parseStatus: {
      pending: "Ожидает",
      parsed: "Разобран",
      empty: "Пусто",
      clarification_required: "Нужно уточнение",
      needs_clarification: "Нужно уточнение",
      completed: "Завершен",
      failed: "Ошибка",
    },
    agentStance: { support: "Поддержать", watch: "Наблюдать", block: "Стоп" },
    accountType: { business: "Бизнес", personal: "Личное", mixed: "Смешанное" },
  },
  kk: {
    names: { ru: "Орысша", kk: "Қазақша", en: "English", uk: "Українська" },
    saved: "Mini App тілі профильге сақталды.",
    previewSaved: "Тіл осы құрылғыда ауыстырылды.",
    saving: "Тіл параметрі сақталуда...",
    failed: "Профиль тілін сақтау мүмкін болмады.",
    settingsHint: "Бұл баптау Mini App тілі мен Telegram жауаптарын бір профильдік тілге синхрондайды.",
    profileLanguage: "Профиль тілі",
    systemNotesTitle: "Жүйелік ескертпелер",
    systemNotesBody: "Жергілікті орта, actor headers және соңғы жаңарту уақыты.",
    apiLabel: "API",
    userLabel: "Пайдаланушы",
    asOfLabel: "Өзекті уақыты",
    browserPreview: "Импорт деректері",
    fileLabel: "Файл",
    receiptFallback: "Чек",
    flowItems: "қозғалыс",
    leftLabel: "қалды",
    paybackDays: "Өтелім",
    projectionEmpty: "Транзакция тарихы жиналғаннан кейін график көрінеді.",
    parseStatus: {
      pending: "Күтуде",
      parsed: "Талданды",
      empty: "Бос",
      clarification_required: "Нақтылау керек",
      needs_clarification: "Нақтылау керек",
      completed: "Аяқталды",
      failed: "Қате",
    },
    agentStance: { support: "Қолдау", watch: "Бақылау", block: "Тоқтату" },
    accountType: { business: "Бизнес", personal: "Жеке", mixed: "Аралас" },
  },
  en: {
    names: { ru: "Russian", kk: "Kazakh", en: "English", uk: "Ukrainian" },
    saved: "Mini App language saved to the profile.",
    previewSaved: "Language switched on this device.",
    saving: "Saving language preference...",
    failed: "Unable to save the profile language.",
    settingsHint: "This setting keeps the Mini App language and Telegram replies aligned for this profile.",
    profileLanguage: "Profile language",
    systemNotesTitle: "System notes",
    systemNotesBody: "Local environment wiring, actor headers, and the latest dashboard timestamp.",
    apiLabel: "API",
    userLabel: "User",
    asOfLabel: "As of",
    browserPreview: "Import details",
    fileLabel: "File",
    receiptFallback: "Receipt",
    flowItems: "flow items",
    leftLabel: "left",
    paybackDays: "Payback",
    projectionEmpty: "Projection will appear after transaction history accumulates.",
    parseStatus: {
      pending: "Pending",
      parsed: "Parsed",
      empty: "Empty",
      clarification_required: "Needs clarification",
      needs_clarification: "Needs clarification",
      completed: "Completed",
      failed: "Failed",
    },
    agentStance: { support: "Support", watch: "Watch", block: "Block" },
    accountType: { business: "Business", personal: "Personal", mixed: "Mixed" },
  },
  uk: {
    names: { ru: "Російська", kk: "Казахська", en: "English", uk: "Українська" },
    saved: "Мову Mini App збережено в профілі.",
    previewSaved: "Мову перемкнено на цьому пристрої.",
    saving: "Зберігаю мовне налаштування...",
    failed: "Не вдалося зберегти мову профілю.",
    settingsHint: "Це налаштування синхронізує мову Mini App і Telegram-відповіді для профілю.",
    profileLanguage: "Мова профілю",
    systemNotesTitle: "Системні нотатки",
    systemNotesBody: "Локальне середовище, actor headers і час останнього зведення.",
    apiLabel: "API",
    userLabel: "Користувач",
    asOfLabel: "Станом на",
    browserPreview: "Деталі імпорту",
    fileLabel: "Файл",
    receiptFallback: "Чек",
    flowItems: "рухів",
    leftLabel: "залишилось",
    paybackDays: "Окупність",
    projectionEmpty: "Графік з'явиться після накопичення історії транзакцій.",
    parseStatus: {
      pending: "Очікує",
      parsed: "Розібрано",
      empty: "Порожньо",
      clarification_required: "Потрібне уточнення",
      needs_clarification: "Потрібне уточнення",
      completed: "Завершено",
      failed: "Помилка",
    },
    agentStance: { support: "Підтримати", watch: "Слідкувати", block: "Стоп" },
    accountType: { business: "Бізнес", personal: "Особисте", mixed: "Змішане" },
  },
};

const statementWorkbenchCopy: Record<Language, StatementWorkbenchCopy> = {
  ru: {
    importTitle: "Мастерская выписок",
    importBody: "Вставьте строки банковской выписки, чтобы импортировать их локально и разобрать неясные переводы прямо в Mini App.",
    draftPlaceholder: "2026-08-10 Client LLP +150000 аванс",
    importAction: "Импортировать выписку",
    importBusy: "Импортируем...",
    uploadAction: "Загрузить файл выписки",
    uploadBusy: "Загружаем файл...",
    uploadHint: "Поддерживаются PDF, CSV, XLSX и XLS. Файлы проходят через тот же контур уточнений, что и в Telegram.",
    sampleAction: "Загрузить пример",
    previewHint: "Откройте Mini App в Telegram, чтобы импортировать выписки в свой контур данных.",
    activeUser: "Пользователь Telegram:",
    livePrompt: "Живое уточнение",
    replyPlaceholder: "Введите ответ вроде business parts или personal family",
    sendReply: "Отправить ответ",
    quickChoices: "Быстрые варианты",
    suggestedBadge: "Подсказка",
    textReplyHint: "Текстовые ответы используют ту же память классификатора, что и Telegram-бот.",
    importFirst: "Сначала импортируйте выписку, чтобы открыть контур уточнений.",
    workbenchIdle: "Нет активных уточнений",
    workbenchIdleBody: "Если импорт оставит неоднозначный перевод, следующий вопрос сразу появится здесь.",
    statusTitle: "Статус последней выписки",
    statusBody: "Этот снимок повторяет живое состояние импорта, с которым сейчас работает Telegram-бот.",
    refreshAction: "Обновить статус",
    importedLabel: "Импортировано",
    parsedLabel: "Разобрано строк",
    autoLabel: "Автокатегоризировано",
    openLabel: "Открыто уточнений",
    historyTitle: "Недавние импорты",
    historyBody: "Каждый локальный импорт выписки отображается здесь с текущим состоянием классификации.",
    historyEmpty: "Импортов выписок пока нет.",
    historyResumeAction: "Вернуться к уточнению",
    historyResumeHint: "По этому импорту еще есть открытые вопросы. Вернитесь в мастерскую выше или продолжите в Telegram.",
    historyResumeNotice: "Активная выписка возвращена в живую очередь уточнений.",
    sourceDownloadAction: "Скачать исходник",
    sourceDownloadBusy: "Готовим файл...",
    sourceDownloaded: "Исходник выписки подготовлен к скачиванию.",
    sampleLoaded: "Пример выписки загружен в мастерскую.",
    statusRefreshed: "Статус выписки обновлен.",
  },
  kk: {
    importTitle: "Үзінді шеберханасы",
    importBody: "Банк үзіндісінің жолдарын осы жерге қойып, оларды жергілікті түрде импорттаңыз және түсініксіз аударымдарды Mini App ішінен шықпай-ақ нақтылаңыз.",
    draftPlaceholder: "2026-08-10 Client LLP +150000 аванс",
    importAction: "Үзіндіні импорттау",
    importBusy: "Импортталып жатыр...",
    uploadAction: "Үзінді файлын жүктеу",
    uploadBusy: "Файл жүктеліп жатыр...",
    uploadHint: "PDF, CSV, XLSX және XLS қолдау табады. Файл импорты Telegram-дегі сол бір нақтылау қозғалтқышын қолданады.",
    sampleAction: "Үлгіні жүктеу",
    previewHint: "Үзіндіні өз контурыңызға импорттау үшін Mini App-ты Telegram ішінде ашыңыз.",
    activeUser: "Telegram пайдаланушысы:",
    livePrompt: "Тікелей нақтылау",
    replyPlaceholder: "business parts немесе personal family сияқты жауап жазыңыз",
    sendReply: "Жауапты жіберу",
    quickChoices: "Жылдам таңдаулар",
    suggestedBadge: "Ұсыныс",
    textReplyHint: "Мәтіндік жауаптар Telegram ботындағыдай классификатор жадын пайдаланады.",
    importFirst: "Нақтылау циклын ашу үшін алдымен үзіндіні импорттаңыз.",
    workbenchIdle: "Белсенді нақтылау жоқ",
    workbenchIdleBody: "Егер импорт күмәнді аударымды қалдырса, келесі сұрақ осы жерде бірден пайда болады.",
    statusTitle: "Соңғы үзіндінің күйі",
    statusBody: "Бұл көрініс Telegram ботындағы нақтылау циклында қолданылып жатқан тірі импорт күйін қайталайды.",
    refreshAction: "Күйді жаңарту",
    importedLabel: "Импортталды",
    parsedLabel: "Талданған жолдар",
    autoLabel: "Авто-санатталған",
    openLabel: "Ашық нақтылаулар",
    historyTitle: "Соңғы импорттар",
    historyBody: "Әр жергілікті үзінді импорты осы жерде өзінің соңғы жіктеу күйімен көрінеді.",
    historyEmpty: "Әзірге үзінді импорты жоқ.",
    historyResumeAction: "Нақтылауға оралу",
    historyResumeHint: "Бұл импорт бойынша әлі ашық сұрақтар бар. Жоғарыдағы шеберханада жалғастырыңыз немесе Telegram-ға өтіңіз.",
    historyResumeNotice: "Белсенді үзінді тірі нақтылау кезегіне қайта ашылды.",
    sourceDownloadAction: "Бастапқы файлды жүктеу",
    sourceDownloadBusy: "Файл дайындалып жатыр...",
    sourceDownloaded: "Үзіндінің бастапқы көзі жүктеуге дайын.",
    sampleLoaded: "Үзінді үлгісі шеберханаға жүктелді.",
    statusRefreshed: "Үзінді күйі жаңартылды.",
  },
  en: {
    importTitle: "Statement workbench",
    importBody: "Paste raw statement lines here to import them locally and resolve unclear transfers without leaving the Mini App.",
    draftPlaceholder: "2026-08-10 Client LLP +150000 advance payment",
    importAction: "Import statement",
    importBusy: "Importing...",
    uploadAction: "Upload statement file",
    uploadBusy: "Uploading file...",
    uploadHint: "PDF, CSV, XLSX, or XLS. File imports use the same clarification engine as Telegram.",
    sampleAction: "Load sample",
    previewHint: "Open the Mini App inside Telegram to import statements into your own workspace.",
    activeUser: "Telegram user:",
    livePrompt: "Live clarification",
    replyPlaceholder: "Type a reply like business parts or personal family",
    sendReply: "Send typed reply",
    quickChoices: "Quick choices",
    suggestedBadge: "Suggested",
    textReplyHint: "Text replies use the same classifier memory as the Telegram bot.",
    importFirst: "Import a statement first to open a clarification loop.",
    workbenchIdle: "No pending clarification",
    workbenchIdleBody: "Once an import leaves an ambiguous transfer, the next question will appear here instantly.",
    statusTitle: "Latest statement status",
    statusBody: "This snapshot mirrors the live import state used by the Telegram bot clarification loop.",
    refreshAction: "Refresh status",
    importedLabel: "Imported",
    parsedLabel: "Parsed items",
    autoLabel: "Auto-categorized",
    openLabel: "Open clarifications",
    historyTitle: "Recent imports",
    historyBody: "Every local statement import appears here with its latest classification state.",
    historyEmpty: "No statement imports yet.",
    historyResumeAction: "Resume in workbench",
    historyResumeHint: "This import still has open questions. Resume in the live workbench above or continue in Telegram.",
    historyResumeNotice: "Active statement returned to the live clarification lane.",
    sourceDownloadAction: "Download source",
    sourceDownloadBusy: "Preparing file...",
    sourceDownloaded: "Statement source is ready to download.",
    sampleLoaded: "Sample statement loaded into the workbench.",
    statusRefreshed: "Statement status refreshed.",
  },
  uk: {
    importTitle: "Майстерня виписок",
    importBody: "Вставте рядки банківської виписки, щоб імпортувати їх локально та розібрати неясні перекази прямо в Mini App.",
    draftPlaceholder: "2026-08-10 Client LLP +150000 аванс",
    importAction: "Імпортувати виписку",
    importBusy: "Імпортуємо...",
    uploadAction: "Завантажити файл виписки",
    uploadBusy: "Завантажуємо файл...",
    uploadHint: "Підтримуються PDF, CSV, XLSX та XLS. Імпорт файлів використовує той самий контур уточнень, що й у Telegram.",
    sampleAction: "Завантажити приклад",
    previewHint: "Відкрийте Mini App у Telegram, щоб імпортувати виписки у власний контур даних.",
    activeUser: "Користувач Telegram:",
    livePrompt: "Живе уточнення",
    replyPlaceholder: "Введіть відповідь на кшталт business parts або personal family",
    sendReply: "Надіслати відповідь",
    quickChoices: "Швидкі варіанти",
    suggestedBadge: "Підказка",
    textReplyHint: "Текстові відповіді використовують ту саму пам'ять класифікатора, що й Telegram-бот.",
    importFirst: "Спочатку імпортуйте виписку, щоб відкрити контур уточнень.",
    workbenchIdle: "Немає активних уточнень",
    workbenchIdleBody: "Якщо імпорт залишить неоднозначний переказ, наступне запитання відразу з'явиться тут.",
    statusTitle: "Статус останньої виписки",
    statusBody: "Цей знімок відображає живий стан імпорту, з яким зараз працює Telegram-бот.",
    refreshAction: "Оновити статус",
    importedLabel: "Імпортовано",
    parsedLabel: "Розібрано рядків",
    autoLabel: "Автокатегоризовано",
    openLabel: "Відкрито уточнень",
    historyTitle: "Останні імпорти",
    historyBody: "Кожен локальний імпорт виписки з'являється тут зі своїм поточним станом класифікації.",
    historyEmpty: "Імпортів виписок поки немає.",
    historyResumeAction: "Повернутися до уточнення",
    historyResumeHint: "У цьому імпорті ще залишилися відкриті питання. Продовжуйте у workbench вище або перейдіть у Telegram.",
    historyResumeNotice: "Активну виписку повернуто в живу чергу уточнень.",
    sourceDownloadAction: "Завантажити джерело",
    sourceDownloadBusy: "Готуємо файл...",
    sourceDownloaded: "Джерело виписки готове до завантаження.",
    sampleLoaded: "Приклад виписки завантажено в майстерню.",
    statusRefreshed: "Статус виписки оновлено.",
  },
};

const quickCaptureExamplesByLanguage: Record<Language, QuickCaptureExamples> = {
  ru: {
    income: "+150000 аванс",
    expense: "17000 касса",
    alt: "-4500 такси",
  },
  kk: {
    income: "+150000 аванс",
    expense: "17000 касса",
    alt: "-4500 такси",
  },
  en: {
    income: "+150000 advance",
    expense: "17000 cash desk",
    alt: "-4500 taxi",
  },
  uk: {
    income: "+150000 аванс",
    expense: "17000 каса",
    alt: "-4500 таксі",
  },
};

const quickCaptureCopy: Record<Language, QuickCaptureCopy> = {
  ru: {
    title: "Быстрый ввод",
    body: "Введите расход, доход или вопрос по своим тратам так, как вы бы отправили его в Telegram.",
    heroKicker: "Голос / Текст",
    closeAction: "Закрыть",
    placeholder: "17000 касса или Сколько ушло на такси?",
    submit: "Сохранить запись",
    submitBusy: "Сохраняю...",
    loadIncome: "Загрузить пример дохода",
    loadExpense: "Загрузить пример расхода",
    accountTitle: "Контур счета",
    accountBusiness: "Бизнес",
    accountPersonal: "Личное",
    previewHint: "Откройте Mini App внутри Telegram, чтобы сохранять операции и задавать вопросы по своим данным.",
    assistantTitle: "Ответ ИИ",
    samplesTitle: "Быстрые примеры",
    resultTitle: "Последний ввод",
    routeLabel: "Маршрут парсера",
    receiptTitle: "Загрузка чека",
    receiptBody: "Прикрепите фото из супермаркета, чтобы запустить локальный OCR, сохранить корзину и обновить трекер SKU-инфляции.",
    receiptCta: "Загрузить фото чека",
    receiptBusy: "Загружаю чек...",
    receiptHint: "JPG, PNG, WEBP или HEIC. Разобранная корзина появится в Кассе и здесь после синхронизации.",
    receiptReady: "Последняя корзина",
  },
  kk: {
    title: "Жедел енгізу",
    body: "Telegram-да жіберетіндей шығыс, кіріс немесе өз шығындарыңыз туралы сұрақ енгізіңіз.",
    heroKicker: "Дауыс / Мәтін",
    closeAction: "Жабу",
    placeholder: "17000 касса",
    submit: "Жазбаны сақтау",
    submitBusy: "Сақталуда...",
    loadIncome: "Кіріс үлгісін жүктеу",
    loadExpense: "Шығыс үлгісін жүктеу",
    accountTitle: "Шот бағыты",
    accountBusiness: "Бизнес",
    accountPersonal: "Жеке",
    previewHint: "Операцияларды сақтау және өз деректеріңіз бойынша сұрақ қою үшін Mini App-ты Telegram ішінде ашыңыз.",
    assistantTitle: "AI жауабы",
    samplesTitle: "Жылдам мысалдар",
    resultTitle: "Соңғы енгізу",
    routeLabel: "Парсер бағыты",
    receiptTitle: "Чек жүктеу",
    receiptBody: "Жергілікті OCR іске қосу, себетті сақтау және SKU инфляция трегін жаңарту үшін супермаркет фотосын тіркеңіз.",
    receiptCta: "Чек фотосын жүктеу",
    receiptBusy: "Чек жүктелуде...",
    receiptHint: "JPG, PNG, WEBP немесе HEIC. Талданған себет Кассада және осында синхроннан кейін көрінеді.",
    receiptReady: "Соңғы себет",
  },
  en: {
    title: "Quick capture",
    body: "Enter an expense, income, or a question about your own spending the way you would send it in Telegram.",
    heroKicker: "Voice / Text",
    closeAction: "Close",
    placeholder: "17000 cash desk",
    submit: "Save entry",
    submitBusy: "Saving...",
    loadIncome: "Load income sample",
    loadExpense: "Load expense sample",
    accountTitle: "Account lane",
    accountBusiness: "Business",
    accountPersonal: "Personal",
    previewHint: "Open the Mini App inside Telegram to save transactions and ask questions about your own data.",
    assistantTitle: "AI answer",
    samplesTitle: "Fast examples",
    resultTitle: "Latest capture",
    routeLabel: "Parser route",
    receiptTitle: "Receipt drop",
    receiptBody: "Attach a supermarket photo to run local OCR, persist the basket, and refresh the SKU inflation lane.",
    receiptCta: "Upload receipt photo",
    receiptBusy: "Uploading receipt...",
    receiptHint: "JPG, PNG, WEBP, or HEIC. The parsed basket will appear in Cashier and here after sync.",
    receiptReady: "Latest basket",
  },
  uk: {
    title: "Швидке внесення",
    body: "Введіть витрату, дохід або запитання по власних витратах так, як ви б надіслали це в Telegram.",
    heroKicker: "Голос / Текст",
    closeAction: "Закрити",
    placeholder: "17000 каса",
    submit: "Зберегти запис",
    submitBusy: "Зберігаю...",
    loadIncome: "Завантажити приклад доходу",
    loadExpense: "Завантажити приклад витрати",
    accountTitle: "Контур рахунку",
    accountBusiness: "Бізнес",
    accountPersonal: "Особисте",
    previewHint: "Відкрийте Mini App у Telegram, щоб зберігати операції та ставити запитання по власних даних.",
    assistantTitle: "Відповідь ШІ",
    samplesTitle: "Швидкі приклади",
    resultTitle: "Останнє внесення",
    routeLabel: "Маршрут парсера",
    receiptTitle: "Завантаження чека",
    receiptBody: "Додайте фото з супермаркету, щоб запустити локальний OCR, зберегти кошик і оновити трекер SKU-інфляції.",
    receiptCta: "Завантажити фото чека",
    receiptBusy: "Завантажую чек...",
    receiptHint: "JPG, PNG, WEBP або HEIC. Розібраний кошик з'явиться в Касі й тут після синхронізації.",
    receiptReady: "Останній кошик",
  },
};

const sandboxCopy: Record<Language, SandboxCopy> = {
  ru: {
    lag: "Лаг до возврата",
    probability: "PoS",
    verdict: "Вердикт",
    liveRationaleTitle: "Живой арбитр",
    liveRationaleBody: "Backend-скоринг учитывает текущий бизнес-баланс, резерв и обязательства перед тем, как вынести вердикт.",
    modelingBusy: "Арбитр обновляется...",
    runwayInside: "Внутри коридора",
    runwayTight: "Коридор сжат",
    runwayOutside: "Вне коридора",
    approve: "Одобрить",
    stage: "Отложить",
    hold: "Пауза",
    noPreview: "Подвигайте слайдеры, чтобы запустить живой сценарий.",
    pressureDelta: "Просадка вниз",
  },
  kk: {
    lag: "Қайтарымға дейінгі лаг",
    probability: "PoS",
    verdict: "Үкім",
    liveRationaleTitle: "Тікелей арбитр",
    liveRationaleBody: "Backend скорингі үкім шығармай тұрып ағымдағы бизнес балансын, резервті және міндеттемелерді есепке алады.",
    modelingBusy: "Арбитр жаңартылуда...",
    runwayInside: "Дәліз ішінде",
    runwayTight: "Дәліз тарылып тұр",
    runwayOutside: "Дәлізден тыс",
    approve: "Мақұлдау",
    stage: "Кейінге қалдыру",
    hold: "Күту",
    noPreview: "Тірі сценарийді іске қосу үшін сырғытпаларды жылжытыңыз.",
    pressureDelta: "Төмендеу серпіні",
  },
  en: {
    lag: "Lag to return",
    probability: "PoS",
    verdict: "Verdict",
    liveRationaleTitle: "Live Arbiter",
    liveRationaleBody: "Backend scoring uses the current business balance, reserve, and obligations before it issues a verdict.",
    modelingBusy: "Refreshing arbiter...",
    runwayInside: "Inside corridor",
    runwayTight: "Tight corridor",
    runwayOutside: "Outside corridor",
    approve: "Approve",
    stage: "Stage it",
    hold: "Hold",
    noPreview: "Move the sliders to run a live scenario.",
    pressureDelta: "Downside swing",
  },
  uk: {
    lag: "Лаг до повернення",
    probability: "PoS",
    verdict: "Вердикт",
    liveRationaleTitle: "Живий арбітр",
    liveRationaleBody: "Backend-скоринг враховує поточний бізнес-баланс, резерв і зобов'язання перед тим, як винести вердикт.",
    modelingBusy: "Арбітр оновлюється...",
    runwayInside: "Усередині коридору",
    runwayTight: "Коридор звужений",
    runwayOutside: "Поза коридором",
    approve: "Схвалити",
    stage: "Відкласти",
    hold: "Пауза",
    noPreview: "Посуньте повзунки, щоб запустити живий сценарій.",
    pressureDelta: "Просідання вниз",
  },
};

const languageOptions: Language[] = ["ru", "kk", "en", "uk"];

const tabs: Array<{ id: TabId; label: Record<Language, string>; icon: string }> = [
  {
    id: "map",
    label: { ru: "Карта", kk: "Карта", en: "Map", uk: "Мапа" },
    icon: "🗺️",
  },
  {
    id: "cashier",
    label: { ru: "Финансы", kk: "Қаржы", en: "Finance", uk: "Фінанси" },
    icon: "📊",
  },
  {
    id: "quick",
    label: { ru: "Ввод", kk: "Енгізу", en: "Quick", uk: "Ввід" },
    icon: "🎙️",
  },
  {
    id: "sandbox",
    label: { ru: "Песочница", kk: "Сынақ", en: "Sandbox", uk: "Пісочниця" },
    icon: "🎯",
  },
  {
    id: "settings",
    label: { ru: "Настройки", kk: "Баптау", en: "Settings", uk: "Налаштування" },
    icon: "⚙️",
  },
];

const cashierCopy: Record<
  Language,
  {
    receiptLane: string;
    receiptBody: string;
    receiptsWindow: string;
    receiptSpend: string;
    trackedSkus: string;
    inflationTracker: string;
    latestBasket: string;
    noInflation: string;
    noReceiptHistory: string;
    priceJump: string;
    previousPrice: string;
    stable: string;
    flowAndActions: string;
  }
> = {
  ru: {
    receiptLane: "Контур чеков",
    receiptBody: "OCR чеков, суммы корзин и движение SKU-инфляции по последним покупкам.",
    receiptsWindow: "Чеки 60д",
    receiptSpend: "Расход по чекам",
    trackedSkus: "SKU в трекинге",
    inflationTracker: "Трекер SKU-инфляции",
    latestBasket: "Последняя корзина",
    noInflation: "Движение цен появится после повторного захвата одинаковых SKU.",
    noReceiptHistory: "Разобранных чеков пока нет. Отправьте фото из супермаркета в бота, чтобы запустить трекер.",
    priceJump: "Скачок цены",
    previousPrice: "Прошлая цена",
    stable: "Стабильно",
    flowAndActions: "Поток и действия",
  },
  kk: {
    receiptLane: "Чек контуры",
    receiptBody: "Соңғы чектер бойынша OCR, себет сомалары және SKU инфляциясының қозғалысы.",
    receiptsWindow: "Чектер 60к",
    receiptSpend: "Чек шығысы",
    trackedSkus: "Бақыланатын SKU",
    inflationTracker: "SKU инфляция трегі",
    latestBasket: "Соңғы себет",
    noInflation: "Баға қозғалысы бірдей SKU қайта түскеннен кейін көрінеді.",
    noReceiptHistory: "Талданған чектер әлі жоқ. Тректі бастау үшін ботқа супермаркет фотосын жіберіңіз.",
    priceJump: "Баға секірісі",
    previousPrice: "Алдыңғы баға",
    stable: "Тұрақты",
    flowAndActions: "Ағын мен әрекеттер",
  },
  en: {
    receiptLane: "Receipt lane",
    receiptBody: "OCR receipts, basket totals, and SKU inflation movement from recent checks.",
    receiptsWindow: "Receipts 60d",
    receiptSpend: "Receipt spend",
    trackedSkus: "Tracked SKUs",
    inflationTracker: "SKU inflation tracker",
    latestBasket: "Latest basket",
    noInflation: "Price movement will appear after repeated SKUs are captured.",
    noReceiptHistory: "No parsed receipts yet. Send a supermarket photo to the bot to start the tracker.",
    priceJump: "Price jump",
    previousPrice: "Previous",
    stable: "Stable",
    flowAndActions: "Flow and actions",
  },
  uk: {
    receiptLane: "Контур чеків",
    receiptBody: "OCR чеків, суми кошиків і рух SKU-інфляції за останніми покупками.",
    receiptsWindow: "Чеки 60д",
    receiptSpend: "Витрати по чеках",
    trackedSkus: "SKU у трекінгу",
    inflationTracker: "Трекер SKU-інфляції",
    latestBasket: "Останній кошик",
    noInflation: "Рух цін з'явиться після повторного захоплення однакових SKU.",
    noReceiptHistory: "Розібраних чеків поки немає. Надішліть фото з супермаркету в бота, щоб запустити трекер.",
    priceJump: "Стрибок ціни",
    previousPrice: "Попередня ціна",
    stable: "Стабільно",
    flowAndActions: "Потік і дії",
  },
};

const copy = {
  ru: {
    eyebrow: "QALTAM / FOCUS 2.0",
    title: "Финансовый навигатор для ежедневного ритма предпринимателя",
    subtitle:
      "Карта мостов, кассовый коридор, банковые импорты и живой контур уточнений в одном локальном Mini App.",
    sync: "Обновить",
    syncing: "Синхронизация...",
    noData: "Данных пока нет",
    syncIssue: "Не удалось получить свежие данные с backend. Показываю оболочку и последние локальные значения.",
    balance: "Общий баланс",
    business: "Бизнес",
    personal: "Личное",
    income30: "Поступления 30д",
    expense30: "Расходы 30д",
    bridges: "11 операционных мостов",
    statements: "Импортов",
    clarifications: "Открытых уточнений",
    safeToWithdraw: "Безопасно вывести",
    reserve: "Резерв",
    obligations: "Обязательства",
    gap: "Риск разрыва",
    projection: "30-дневная проекция",
    recentFlow: "Последние движения",
    pressurePlan: "Антикризисный контур",
    quickTitle: "Интерактивный контур уточнений",
    quickBody:
      "Если statement import оставил неясные переводы, здесь видно текущий вопрос и накопленную память правил.",
    replyHint: "Ответьте в Telegram текстом или голосом, чтобы сохранить правило навсегда.",
    learnedRules: "Выученные правила",
    lastImport: "Последний импорт",
    sandboxTitle: "What-if лаборатория",
    sandboxBody:
      "Пока scoring engine еще расширяется, можно быстро проверить нагрузку на кассу и ожидаемый возврат.",
    invest: "Инвестиция",
    roi: "Ожидаемый ROI",
    payback: "Ожидаемый возврат",
    runway: "Давление на кассу",
    settingsTitle: "Контур управления",
    settingsBody:
      "Язык, локальные интеграции, Mini App URL и iOS shortcut endpoint доступны здесь для быстрого доступа.",
    language: "Язык",
    profile: "Профиль",
    onboarding: "Онбординг",
    complete: "завершен",
    pending: "в процессе",
    quickAdd: "Quick Add endpoint",
    webApp: "WebApp URL",
    settingsShortcutTitle: "Apple Shortcuts / Quick Add",
    settingsShortcutBody:
      "Локальный endpoint уже готов для iPhone Shortcut: можно слать raw_text вроде '+150000 avans' или структурированный payload через X-API-KEY.",
    settingsShortcutMode: "Режим",
    settingsShortcutLinked: "Mini App связан с Telegram actor",
    settingsShortcutPreview: "Shortcut API вне Telegram",
    settingsShortcutHeaders: "Заголовки",
    settingsShortcutPayload: "Пример payload",
    settingsShortcutCurl: "Быстрый curl",
    settingsShortcutOpen: "Открыть Mini App",
    settingsShortcutApiKey: "Нужен локальный X-API-KEY для Shortcut вне Telegram.",
    settingsQalTitle: "$QAL Proof of Care",
    settingsQalBody:
      "Живая сводка сигналов care по данным текущего пользователя. Это внутренний индикатор контура, а не ончейн-баланс.",
    settingsQalBadge: "Живой контур",
    settingsQalScore: "Care score",
    settingsQalMint: "Условный mint window",
    settingsQalSignals: "Подключенные сигналы",
    settingsQalStatus: "Статус контура",
    settingsQalEligible: "контур в норме",
    settingsQalHold: "удержать до закрытия неясностей",
    settingsQalBooting: "контур еще набирает сигналы",
    settingsMarketTitle: "Qaltam Market",
    settingsMarketBody:
      "Локальная витрина рекомендаций: что имеет смысл включить, купить или довести до ритуала по текущему финансовому контексту.",
    settingsMarketEmpty: "Рынок пока тихий: после новых данных появятся более точные рекомендации.",
    settingsMarketNow: "сейчас",
    settingsMarketNext: "следом",
    settingsMarketWatch: "наблюдать",
    settingsMarketClarificationsTitle: "Спринт уточнений P2P",
    settingsMarketClarificationsOpen: "Остались открытые уточнения по переводам. Лучше закрыть их первым, чтобы память правил и автоклассификация стали сильнее.",
    settingsMarketClarificationsClear: "Очередь уточнений чистая. Можно усиливать автопамять новыми statement import без ручного шума.",
    settingsMarketReceiptsTitle: "OCR чеков и SKU-трекер",
    settingsMarketReceiptsMissing: "Чеков пока нет. Один supermarket receipt сразу откроет корзину, SKU-инфляцию и более живую кассовую картину.",
    settingsMarketReceiptsReady: "Контур чеков уже дышит. Следующий шаг - удерживать повторяемость покупок для более честного инфляционного трека.",
    settingsMarketRunwayTitle: "Контур кассовой защиты",
    settingsMarketRunwayGap: "Есть признак cash gap или антикризисного сценария. Стоит закрепить Safe-to-Withdraw ритуал и план действий на 30 дней.",
    settingsMarketRunwayStable: "Разрыв пока не просматривается. Можно переключить внимание на гипотезы роста и дисциплину ежедневного offload.",
    settingsMarketShortcutsTitle: "iPhone offload shortcut",
    settingsMarketShortcutsBody: "Shortcut endpoint уже локально доступен. Подключение голосового или текстового offload на iPhone сократит трение ежедневного ввода.",
    mapLead: "Операционные сектора, куда сейчас уходит или откуда приходит деньги.",
    pendingClarification: "Ожидает ответ",
    noClarification: "Сейчас все спорные переводы уже разобраны.",
    openBot: "Продолжить в Telegram",
    source: "Источник",
    status: "Статус",
    accountMix: "Карманная структура",
    noTransactions: "Последних движений пока нет.",
    noRules: "Память правил пока пустая.",
    uploadTip: "Загрузите PDF / CSV / XLSX statement в бота, и он появится здесь.",
  },
  kk: {
    eyebrow: "QALTAM / FOCUS 2.0",
    title: "Кәсіпкердің күнделікті ырғағына арналған қаржылық навигатор",
    subtitle:
      "Көпір картасы, кассалық дәліз, банк импорттары және нақтылау контуры бір жерге жиналды.",
    sync: "Жаңарту",
    syncing: "Жаңартылуда...",
    noData: "Әзірге дерек жоқ",
    syncIssue: "Backend-пен байланыс үзілді. Қабық пен соңғы жергілікті мәндер көрсетіліп тұр.",
    balance: "Жалпы баланс",
    business: "Бизнес",
    personal: "Жеке",
    income30: "30 күн кіріс",
    expense30: "30 күн шығыс",
    bridges: "11 операциялық көпір",
    statements: "Импорттар",
    clarifications: "Ашық нақтылаулар",
    safeToWithdraw: "Қауіпсіз алу",
    reserve: "Резерв",
    obligations: "Міндеттемелер",
    gap: "Үзіліс тәуекелі",
    projection: "30 күндік проекция",
    recentFlow: "Соңғы қозғалыстар",
    pressurePlan: "Дағдарыс контуры",
    quickTitle: "Нақтылау контуры",
    quickBody:
      "Statement import түсініксіз аударым қалдырса, осы жерден сұрақ пен есте сақталған ережелерді көресіз.",
    replyHint: "Ережені мәңгі сақтау үшін Telegram-да мәтінмен не дауыспен жауап беріңіз.",
    learnedRules: "Үйренген ережелер",
    lastImport: "Соңғы импорт",
    sandboxTitle: "What-if зертханасы",
    sandboxBody:
      "Scoring engine әлі кеңейіп жатыр, бірақ қазірдің өзінде кассаға түсетін қысымды тез есептей аламыз.",
    invest: "Инвестиция",
    roi: "Күтілетін ROI",
    payback: "Күтілетін қайтарым",
    runway: "Кассаға қысым",
    settingsTitle: "Басқару контуры",
    settingsBody:
      "Тіл, жергілікті интеграциялар, Mini App URL және iOS shortcut endpoint осы бетте жиналған.",
    language: "Тіл",
    profile: "Профиль",
    onboarding: "Онбординг",
    complete: "аяқталған",
    pending: "жалғасуда",
    quickAdd: "Quick Add endpoint",
    webApp: "WebApp URL",
    settingsShortcutTitle: "Apple Shortcuts / Quick Add",
    settingsShortcutBody:
      "Жергілікті endpoint iPhone Shortcut үшін дайын: '+150000 avans' сияқты raw_text немесе X-API-KEY арқылы құрылымды payload жіберуге болады.",
    settingsShortcutMode: "Режим",
    settingsShortcutLinked: "Mini App Telegram actor-мен байланысқан",
    settingsShortcutPreview: "Telegram-нан тыс Shortcut API",
    settingsShortcutHeaders: "Тақырыптар",
    settingsShortcutPayload: "Payload үлгісі",
    settingsShortcutCurl: "Жедел curl",
    settingsShortcutOpen: "Mini App ашу",
    settingsShortcutApiKey: "Telegram-нан тыс Shortcut үшін жергілікті X-API-KEY керек.",
    settingsQalTitle: "$QAL Proof of Care",
    settingsQalBody:
      "Ағымдағы пайдаланушы деректеріне негізделген тірі care-сигналдар. Бұл on-chain баланс емес, ішкі контур индикаторы.",
    settingsQalBadge: "Тірі контур",
    settingsQalScore: "Care score",
    settingsQalMint: "Шартты mint window",
    settingsQalSignals: "Қосылған сигналдар",
    settingsQalStatus: "Контур күйі",
    settingsQalEligible: "контур қалыпты",
    settingsQalHold: "анықталмағандар жабылғанша ұстап тұру",
    settingsQalBooting: "контур әлі сигнал жинап жатыр",
    settingsMarketTitle: "Qaltam Market",
    settingsMarketBody:
      "Жергілікті ұсыныстар витринасы: ағымдағы қаржылық контекстке сай нені қосу, сатып алу немесе дағдыға айналдыру маңызды екенін көрсетеді.",
    settingsMarketEmpty: "Нарық әзірге тыныш: жаңа деректерден кейін ұсыныстар нақтыланады.",
    settingsMarketNow: "қазір",
    settingsMarketNext: "келесі",
    settingsMarketWatch: "бақылау",
    settingsMarketClarificationsTitle: "P2P нақтылау спринті",
    settingsMarketClarificationsOpen: "Аударымдар бойынша ашық нақтылаулар бар. Алдымен соны жабу керек, сонда ереже жадысы мен авто-классификация күшейеді.",
    settingsMarketClarificationsClear: "Нақтылау кезегі таза. Енді қолмен шуды көбейтпей, жаңа statement import арқылы автожадыны күшейтуге болады.",
    settingsMarketReceiptsTitle: "Чек OCR және SKU трекері",
    settingsMarketReceiptsMissing: "Чектер әлі жоқ. Бір supermarket receipt бірден себет, SKU инфляциясы және шынайырақ кассалық көрініс ашады.",
    settingsMarketReceiptsReady: "Чек контуры іске қосылған. Келесі қадам - инфляция трегі адал болуы үшін қайталанатын сатып алуларды тұрақтандыру.",
    settingsMarketRunwayTitle: "Касса қорғаныс контуры",
    settingsMarketRunwayGap: "Cash gap не дағдарыс сценарийі белгісі бар. Safe-to-Withdraw ырғағын және 30 күндік әрекет жоспарын бекіткен дұрыс.",
    settingsMarketRunwayStable: "Әзірге үзіліс көрінбейді. Назарды өсу гипотезаларына және күнделікті offload тәртібіне ауыстыруға болады.",
    settingsMarketShortcutsTitle: "iPhone offload shortcut",
    settingsMarketShortcutsBody: "Shortcut endpoint жергілікті ортада дайын. iPhone-дағы дауыстық не мәтіндік offload күнделікті енгізу үйкелісін азайтады.",
    mapLead: "Қазір ақша қай секторға кетіп жатыр немесе қайдан келіп жатыр.",
    pendingClarification: "Жауап күтіп тұр",
    noClarification: "Қазір барлық даулы аударымдар шешілген.",
    openBot: "Telegram-да жалғастыру",
    source: "Дереккөз",
    status: "Күйі",
    accountMix: "Қалта құрылымы",
    noTransactions: "Соңғы қозғалыстар әзірге жоқ.",
    noRules: "Ереже жадысы әзірге бос.",
    uploadTip: "PDF / CSV / XLSX statement файлды ботқа жіберіңіз, ол осында көрінеді.",
  },
  en: {
    eyebrow: "QALTAM / FOCUS 2.0",
    title: "A daily financial cockpit for Kazakhstani entrepreneurs",
    subtitle:
      "Bridge map, cashier corridor, bank imports, and live clarification loops in one local Mini App.",
    sync: "Refresh",
    syncing: "Refreshing...",
    noData: "No data yet",
    syncIssue: "Fresh backend data is unavailable right now. The shell is still usable with the latest local values.",
    balance: "Total balance",
    business: "Business",
    personal: "Personal",
    income30: "30d income",
    expense30: "30d expense",
    bridges: "11 operating bridges",
    statements: "Imports",
    clarifications: "Open clarifications",
    safeToWithdraw: "Safe to withdraw",
    reserve: "Reserve",
    obligations: "Obligations",
    gap: "Gap risk",
    projection: "30-day projection",
    recentFlow: "Recent flow",
    pressurePlan: "Gap action lane",
    quickTitle: "Interactive clarification lane",
    quickBody:
      "When a statement import leaves ambiguous transfers, this tab surfaces the live question and the memory rules already learned.",
    replyHint: "Reply in Telegram by text or voice to save the rule permanently.",
    learnedRules: "Learned rules",
    lastImport: "Latest import",
    sandboxTitle: "What-if lab",
    sandboxBody:
      "The full scoring engine is still growing, but we can already test cash pressure and expected return in a fast local loop.",
    invest: "Investment",
    roi: "Expected ROI",
    payback: "Projected return",
    runway: "Cash pressure",
    settingsTitle: "Control surface",
    settingsBody:
      "Language, local integrations, Mini App URL, and the iOS shortcut endpoint are collected here.",
    language: "Language",
    profile: "Profile",
    onboarding: "Onboarding",
    complete: "complete",
    pending: "in progress",
    quickAdd: "Quick Add endpoint",
    webApp: "WebApp URL",
    settingsShortcutTitle: "Apple Shortcuts / Quick Add",
    settingsShortcutBody:
      "The local endpoint is already ready for an iPhone Shortcut: send raw_text like '+150000 avans' or a structured payload through X-API-KEY.",
    settingsShortcutMode: "Mode",
    settingsShortcutLinked: "Mini App linked to Telegram actor",
    settingsShortcutPreview: "Shortcut API outside Telegram",
    settingsShortcutHeaders: "Headers",
    settingsShortcutPayload: "Sample payload",
    settingsShortcutCurl: "Quick curl",
    settingsShortcutOpen: "Open Mini App",
    settingsShortcutApiKey: "A local X-API-KEY is required for Shortcut calls outside Telegram.",
    settingsQalTitle: "$QAL Proof of Care",
    settingsQalBody:
      "Live care signals based on the current user's data. This is an internal workflow indicator, not an on-chain balance.",
    settingsQalBadge: "Live workflow",
    settingsQalScore: "Care score",
    settingsQalMint: "Indicative mint window",
    settingsQalSignals: "Signals wired",
    settingsQalStatus: "Workflow status",
    settingsQalEligible: "workflow is healthy",
    settingsQalHold: "hold until ambiguity is cleared",
    settingsQalBooting: "still gathering signals",
    settingsMarketTitle: "Qaltam Market",
    settingsMarketBody:
      "A local recommendation shelf showing what is most worth enabling, buying, or ritualizing from the current financial context.",
    settingsMarketEmpty: "The market shelf is quiet for now. New data will unlock sharper recommendations.",
    settingsMarketNow: "now",
    settingsMarketNext: "next",
    settingsMarketWatch: "watch",
    settingsMarketClarificationsTitle: "P2P clarification sprint",
    settingsMarketClarificationsOpen: "There are still open transfer clarifications. Closing them first will strengthen rule memory and auto-classification.",
    settingsMarketClarificationsClear: "The clarification queue is clear. The next gain is feeding new statement imports without adding manual noise.",
    settingsMarketReceiptsTitle: "Receipt OCR and SKU tracker",
    settingsMarketReceiptsMissing: "No receipts have landed yet. A single supermarket receipt unlocks baskets, SKU inflation, and a more faithful cashier picture.",
    settingsMarketReceiptsReady: "The receipt lane is active. The next gain is consistent repeat purchases so the inflation tracker becomes more truthful.",
    settingsMarketRunwayTitle: "Cash protection lane",
    settingsMarketRunwayGap: "A cash gap or crisis scenario is visible. This is the right moment to lock in the Safe-to-Withdraw ritual and a 30-day response plan.",
    settingsMarketRunwayStable: "No gap is visible right now. Attention can shift toward growth hypotheses and consistent daily offload discipline.",
    settingsMarketShortcutsTitle: "iPhone offload shortcut",
    settingsMarketShortcutsBody: "The Shortcut endpoint is already available locally. Wiring voice or text offload on iPhone will cut daily logging friction.",
    mapLead: "Operational sectors where money is currently landing or leaving.",
    pendingClarification: "Awaiting reply",
    noClarification: "All ambiguous transfers are resolved right now.",
    openBot: "Continue in Telegram",
    source: "Source",
    status: "Status",
    accountMix: "Pocket structure",
    noTransactions: "No recent flow yet.",
    noRules: "No saved clarification rules yet.",
    uploadTip: "Upload a PDF / CSV / XLSX statement to the bot and it will appear here.",
  },
  uk: {
    eyebrow: "QALTAM / FOCUS 2.0",
    title: "Щоденний фінансовий навігатор для підприємця",
    subtitle:
      "Карта мостів, касовий коридор, банківські імпорти та живий контур уточнень в одному локальному Mini App.",
    sync: "Оновити",
    syncing: "Оновлення...",
    noData: "Даних поки немає",
    syncIssue: "Свіжі дані з backend зараз недоступні. Оболонка працює з останніми локальними значеннями.",
    balance: "Загальний баланс",
    business: "Бізнес",
    personal: "Особисте",
    income30: "Надходження 30д",
    expense30: "Витрати 30д",
    bridges: "11 операційних мостів",
    statements: "Імпорти",
    clarifications: "Відкриті уточнення",
    safeToWithdraw: "Безпечно вивести",
    reserve: "Резерв",
    obligations: "Зобов'язання",
    gap: "Ризик розриву",
    projection: "30-денна проекція",
    recentFlow: "Останні рухи",
    pressurePlan: "Антикризовий контур",
    quickTitle: "Контур уточнень",
    quickBody:
      "Якщо імпорт виписки залишив неясні перекази, тут видно поточне питання та правила, які система вже вивчила.",
    replyHint: "Відповідайте в Telegram текстом або голосом, щоб правило збереглося назавжди.",
    learnedRules: "Вивчені правила",
    lastImport: "Останній імпорт",
    sandboxTitle: "What-if лабораторія",
    sandboxBody:
      "Scoring engine ще розширюється, але вже зараз можна швидко оцінити тиск на касу та очікуваний результат.",
    invest: "Інвестиція",
    roi: "Очікуваний ROI",
    payback: "Очікуване повернення",
    runway: "Тиск на касу",
    settingsTitle: "Панель керування",
    settingsBody:
      "Мова, локальні інтеграції, Mini App URL та endpoint для iOS shortcut зібрані в одному місці.",
    language: "Мова",
    profile: "Профіль",
    onboarding: "Онбординг",
    complete: "завершено",
    pending: "у процесі",
    quickAdd: "Quick Add endpoint",
    webApp: "WebApp URL",
    settingsShortcutTitle: "Apple Shortcuts / Quick Add",
    settingsShortcutBody:
      "Локальний endpoint уже готовий для iPhone Shortcut: можна надсилати raw_text на кшталт '+150000 avans' або структурований payload через X-API-KEY.",
    settingsShortcutMode: "Режим",
    settingsShortcutLinked: "Mini App прив'язаний до Telegram actor",
    settingsShortcutPreview: "Shortcut API поза Telegram",
    settingsShortcutHeaders: "Заголовки",
    settingsShortcutPayload: "Приклад payload",
    settingsShortcutCurl: "Швидкий curl",
    settingsShortcutOpen: "Відкрити Mini App",
    settingsShortcutApiKey: "Для Shortcut поза Telegram потрібен локальний X-API-KEY.",
    settingsQalTitle: "$QAL Proof of Care",
    settingsQalBody:
      "Живі care-сигнали на основі даних поточного користувача. Це внутрішній індикатор контуру, а не on-chain баланс.",
    settingsQalBadge: "Живий контур",
    settingsQalScore: "Care score",
    settingsQalMint: "Умовний mint window",
    settingsQalSignals: "Підключені сигнали",
    settingsQalStatus: "Стан контуру",
    settingsQalEligible: "контур у нормі",
    settingsQalHold: "утримати до закриття неясностей",
    settingsQalBooting: "контур ще збирає сигнали",
    settingsMarketTitle: "Qaltam Market",
    settingsMarketBody:
      "Локальна вітрина рекомендацій: що зараз найбільш варто ввімкнути, купити або перетворити на ритуал з огляду на поточний фінансовий контекст.",
    settingsMarketEmpty: "Вітрина поки тиха: нові дані відкриють точніші рекомендації.",
    settingsMarketNow: "зараз",
    settingsMarketNext: "далі",
    settingsMarketWatch: "спостерігати",
    settingsMarketClarificationsTitle: "Спринт P2P-уточнень",
    settingsMarketClarificationsOpen: "Є відкриті уточнення щодо переказів. Краще закрити їх першими, щоб посилити пам'ять правил і автокласифікацію.",
    settingsMarketClarificationsClear: "Черга уточнень чиста. Наступний виграш - нові імпорти виписок без зайвого ручного шуму.",
    settingsMarketReceiptsTitle: "OCR чеків і SKU-трекер",
    settingsMarketReceiptsMissing: "Чеків поки немає. Один supermarket receipt одразу відкриє кошики, SKU-інфляцію та чеснішу картину каси.",
    settingsMarketReceiptsReady: "Контур чеків уже активний. Далі варто втримати повторювані покупки, щоб інфляційний трек став правдивішим.",
    settingsMarketRunwayTitle: "Контур захисту каси",
    settingsMarketRunwayGap: "Видно cash gap або кризовий сценарій. Саме час закріпити ритуал Safe-to-Withdraw і 30-денний план відповіді.",
    settingsMarketRunwayStable: "Розриву зараз не видно. Увагу можна змістити на гіпотези росту та сталу щоденну дисципліну offload.",
    settingsMarketShortcutsTitle: "iPhone offload shortcut",
    settingsMarketShortcutsBody: "Shortcut endpoint уже доступний локально. Підключення голосового або текстового offload на iPhone зменшить щоденне тертя вводу.",
    mapLead: "Операційні сектори, куди зараз ідуть або звідки приходять гроші.",
    pendingClarification: "Чекає на відповідь",
    noClarification: "Усі спірні перекази вже розібрані.",
    openBot: "Продовжити в Telegram",
    source: "Джерело",
    status: "Статус",
    accountMix: "Структура кишень",
    noTransactions: "Останніх рухів поки немає.",
    noRules: "Пам'ять правил поки порожня.",
    uploadTip: "Завантажте PDF / CSV / XLSX statement у бота, і він з'явиться тут.",
  },
} as const;

function App() {
  const actor = resolveActorContext();
  const effectiveTelegramUserId = actor.telegramUserId;
  const effectiveTelegramChatId = actor.telegramChatId;
  const initialLanguage = resolveInitialLanguage();
  const initialTabRef = useRef<TabId>(resolveInitialTab());
  const [language, setLanguage] = useState<Language>(initialLanguage);
  const [languageSaving, setLanguageSaving] = useState(false);
  const [languageNotice, setLanguageNotice] = useState<string | null>(null);
  const [languageError, setLanguageError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>(initialTabRef.current);
  const [summarySheetOpen, setSummarySheetOpen] = useState(false);
  const quickSheetOpen = activeTab === "quick";
  const lastNonQuickTabRef = useRef<TabId>(initialTabRef.current === "quick" ? "cashier" : initialTabRef.current);
  const quickSheetDragControls = useDragControls();
  const [dashboard, setDashboard] = useState<DashboardBundle | null>(null);
  const [statementPending, setStatementPending] = useState<StatementPending | null>(null);
  const [statementStatus, setStatementStatus] = useState<StatementStatusSnapshot | null>(null);
  const [statementHistory, setStatementHistory] = useState<StatementHistoryEntry[]>([]);
  const initialStatementIdRef = useRef<number | null>(resolveInitialStatementId());
  const [selectedStatementId, setSelectedStatementId] = useState<number | null>(() => initialStatementIdRef.current);
  const [selectedStatementDetail, setSelectedStatementDetail] = useState<StatementDetail | null>(null);
  const [statementDetailBusy, setStatementDetailBusy] = useState(false);
  const [statementDetailError, setStatementDetailError] = useState<string | null>(null);
  const [quickDraft, setQuickDraft] = useState("");
  const [quickAccountType, setQuickAccountType] = useState<"business" | "personal">("business");
  const [quickBusy, setQuickBusy] = useState(false);
  const [quickNotice, setQuickNotice] = useState<string | null>(null);
  const [quickError, setQuickError] = useState<string | null>(null);
  const [quickResult, setQuickResult] = useState<QuickAddResult | null>(null);
  const [quickAssistantResult, setQuickAssistantResult] = useState<QuickAssistantResult | null>(null);
  const [quickReceiptBusy, setQuickReceiptBusy] = useState(false);
  const [quickReceiptNotice, setQuickReceiptNotice] = useState<string | null>(null);
  const [quickReceiptError, setQuickReceiptError] = useState<string | null>(null);
  const [statementDraft, setStatementDraft] = useState("");
  const [clarificationReply, setClarificationReply] = useState("");
  const deepLinkFocusRef = useRef<DeepLinkFocus | null>(resolveInitialFocus());
  const statementImportCardRef = useRef<HTMLElement | null>(null);
  const statementDetailCardRef = useRef<HTMLElement | null>(null);
  const clarificationCardRef = useRef<HTMLElement | null>(null);
  const [statementBusy, setStatementBusy] = useState(false);
  const [statementDownloadTargetId, setStatementDownloadTargetId] = useState<number | null>(null);
  const [statementNotice, setStatementNotice] = useState<string | null>(null);
  const [statementError, setStatementError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [investment, setInvestment] = useState(180000);
  const [roi, setRoi] = useState(38);
  const [lagDays, setLagDays] = useState(21);
  const [sandboxBusy, setSandboxBusy] = useState(false);
  const [sandboxError, setSandboxError] = useState<string | null>(null);
  const [sandboxResult, setSandboxResult] = useState<HypothesisScoreResponse | null>(null);
  const deferredDashboard = useDeferredValue(dashboard);
  const deferredInvestment = useDeferredValue(investment);
  const deferredRoi = useDeferredValue(roi);
  const deferredLagDays = useDeferredValue(lagDays);
  const text = copy[language];
  const cashierText = cashierCopy[language];
  const statementText = statementWorkbenchCopy[language];
  const quickText = quickCaptureCopy[language];
  const quickExamples = quickCaptureExamplesByLanguage[language];
  const sandboxText = sandboxCopy[language];
  const languageText = miniAppLanguageCopy[language];
  const hasActiveClarificationQueue = Boolean(
    statementPending || (statementStatus?.remaining_clarifications ?? 0) > 0 || dashboard?.micro.pending_clarification,
  );
  const quickSheetDetailOpen = quickSheetOpen && selectedStatementId !== null;
  const quickSheetHasPendingInput = Boolean(quickDraft.trim() || statementDraft.trim() || clarificationReply.trim());
  const quickSheetClosingGuard =
    quickSheetOpen &&
    (quickSheetHasPendingInput ||
      quickBusy ||
      quickReceiptBusy ||
      statementBusy ||
      statementDetailBusy ||
      statementDownloadTargetId !== null);
  const toggleSummarySheet = () => {
    triggerTelegramImpact(summarySheetOpen ? "soft" : "medium");
    startTransition(() => {
      setSummarySheetOpen((current) => !current);
    });
  };
  const closeSummarySheet = () => {
    if (!summarySheetOpen) {
      return;
    }
    triggerTelegramImpact("soft");
    startTransition(() => {
      setSummarySheetOpen(false);
    });
  };
  const closeQuickSheet = () => {
    startTransition(() => setActiveTab(lastNonQuickTabRef.current));
  };
  const resetQuickSheetDetail = () => {
    setSelectedStatementId(null);
    setSelectedStatementDetail(null);
    setStatementDetailError(null);
  };
  const handleTabPress = (tabId: TabId) => {
    if (tabId === "quick") {
      triggerTelegramImpact(quickSheetOpen ? "soft" : "medium");
      startTransition(() => {
        setSummarySheetOpen(false);
        setActiveTab((currentTab) => (currentTab === "quick" ? lastNonQuickTabRef.current : "quick"));
      });
      return;
    }

    if (tabId !== activeTab) {
      triggerTelegramSelectionHaptic();
    }
    startTransition(() => setActiveTab(tabId));
    setSummarySheetOpen(false);
  };
  const handleTelegramBack = useEffectEvent(() => {
    if (quickSheetDetailOpen) {
      triggerTelegramSelectionHaptic();
      resetQuickSheetDetail();
      return;
    }

    if (quickSheetOpen) {
      triggerTelegramImpact("soft");
      closeQuickSheet();
    }
  });

  useEffect(() => {
    const webApp = window.Telegram?.WebApp;
    if (!webApp) {
      return;
    }

    const syncTelegramChrome = () => {
      applyTelegramTheme(webApp.themeParams);
      applyTelegramViewportInsets(webApp.contentSafeAreaInset ?? webApp.safeAreaInset);
      webApp.setBackgroundColor?.("#0b0d12");
      webApp.setHeaderColor?.("#0b0d12");
      webApp.setBottomBarColor?.("#0b0d12");
    };

    const syncTelegramSafeArea = () => {
      applyTelegramViewportInsets(webApp.contentSafeAreaInset ?? webApp.safeAreaInset);
    };

    webApp.ready();
    webApp.expand();
    try {
      webApp.requestFullscreen?.();
    } catch {
      // Ignore unsupported fullscreen requests in browser previews and older Telegram shells.
    }
    syncTelegramChrome();
    webApp.onEvent?.("themeChanged", syncTelegramChrome);
    webApp.onEvent?.("safeAreaChanged", syncTelegramSafeArea);
    webApp.onEvent?.("contentSafeAreaChanged", syncTelegramSafeArea);

    return () => {
      webApp.offEvent?.("themeChanged", syncTelegramChrome);
      webApp.offEvent?.("safeAreaChanged", syncTelegramSafeArea);
      webApp.offEvent?.("contentSafeAreaChanged", syncTelegramSafeArea);
    };
  }, []);

  useEffect(() => {
    syncActiveTabQuery(activeTab);
  }, [activeTab]);

  useEffect(() => {
    syncStatementSelectionQuery(activeTab, selectedStatementId);
  }, [activeTab, selectedStatementId]);

  useEffect(() => {
    if (activeTab !== "quick") {
      lastNonQuickTabRef.current = activeTab;
    }
  }, [activeTab]);

  useEffect(() => {
    const webApp = window.Telegram?.WebApp;
    if (!webApp) {
      return;
    }
    if (quickSheetOpen) {
      webApp.disableVerticalSwipes?.();
      return () => {
        webApp.enableVerticalSwipes?.();
      };
    }
    webApp.enableVerticalSwipes?.();
  }, [quickSheetOpen]);

  useEffect(() => {
    const backButton = window.Telegram?.WebApp?.BackButton;
    if (!backButton) {
      return;
    }

    if (quickSheetOpen) {
      backButton.show?.();
      backButton.onClick?.(handleTelegramBack);
      return () => {
        backButton.offClick?.(handleTelegramBack);
        backButton.hide?.();
      };
    }

    backButton.hide?.();
  }, [quickSheetOpen, quickSheetDetailOpen]);

  useEffect(() => {
    const webApp = window.Telegram?.WebApp;
    if (!webApp) {
      return;
    }

    if (quickSheetClosingGuard) {
      webApp.enableClosingConfirmation?.();
      return () => {
        webApp.disableClosingConfirmation?.();
      };
    }

    webApp.disableClosingConfirmation?.();
  }, [quickSheetClosingGuard]);

  useEffect(() => {
    void refreshDashboard();
  }, []);

  useEffect(() => {
    if (!statementHistory.length) {
      if (selectedStatementId !== null) {
        setSelectedStatementId(null);
      }
      setSelectedStatementDetail(null);
      setStatementDetailError(null);
      return;
    }

    const selectionDecision = resolveStatementHistorySelection({
      statementHistory,
      selectedStatementId,
      initialStatementId: initialStatementIdRef.current,
    });
    if (selectionDecision.consumeInitialStatementId) {
      initialStatementIdRef.current = null;
    }
    if (selectionDecision.nextSelectedStatementId !== selectedStatementId) {
      setSelectedStatementId(selectionDecision.nextSelectedStatementId);
    }
  }, [statementHistory, selectedStatementId]);

  const syncQuickWorkspace = useEffectEvent(async (languageOverride?: Language) => {
    if (!effectiveTelegramUserId) {
      throw new Error(statementText.previewHint);
    }

    const apiBase = resolveApiBaseUrl();
    const microUrl = buildApiUrl(apiBase, "/api/v1/dashboard/micro");
    const statementLanguage = languageOverride ?? language;
    const workbenchUrl = buildApiUrl(apiBase, "/api/v1/statements/workbench", {
      language: statementLanguage,
      limit: 6,
    });
    const [microResult, workbenchResult] = await Promise.all([
      fetchJson<DashboardMicro>(microUrl),
      fetchJson<StatementWorkbenchResponse>(workbenchUrl),
    ]);
    setDashboard((currentDashboard) => {
      const baseDashboard = currentDashboard ?? buildEmptyDashboard(effectiveTelegramUserId);
      return {
        ...baseDashboard,
        micro: microResult,
      };
    });
    setStatementPending(workbenchResult.pending);
    setStatementStatus(workbenchResult.latest_status);
    setStatementHistory(workbenchResult.history);
    if (microResult.preferred_language) {
      const nextLanguage = resolveLanguage(microResult.preferred_language);
      persistLanguagePreference(nextLanguage);
      setLanguage((currentLanguage) => (currentLanguage === nextLanguage ? currentLanguage : nextLanguage));
    }
    return { microResult, workbenchResult };
  });

  useEffect(() => {
    if (activeTab !== "sandbox") {
      return;
    }

    let cancelled = false;

    async function refreshSandboxPreview() {
      const apiBase = resolveApiBaseUrl();
      setSandboxBusy(true);
      setSandboxError(null);
      try {
        const result = await postJson<HypothesisScoreResponse>(`${apiBase}/api/v1/hypotheses/score-preview`, {
          title: "Mini App scenario preview",
          role_perspective: "COO",
          required_investment: deferredInvestment,
          time_lag_days: deferredLagDays,
          expected_roi: (deferredRoi / 100).toFixed(4),
          risk_level: resolveSandboxRiskLevel(deferredRoi, deferredLagDays),
          status: "draft",
          days: 45,
        });
        if (!cancelled) {
          setSandboxResult(result);
        }
      } catch (sandboxPreviewError) {
        if (!cancelled) {
          setSandboxError(sandboxPreviewError instanceof Error ? sandboxPreviewError.message : "Sandbox scoring failed.");
          setSandboxResult(null);
        }
      } finally {
        if (!cancelled) {
          setSandboxBusy(false);
        }
      }
    }

    void refreshSandboxPreview();

    return () => {
      cancelled = true;
    };
  }, [activeTab, deferredInvestment, deferredRoi, deferredLagDays, dashboard]);

  useEffect(() => {
    if (activeTab !== "quick" || !effectiveTelegramUserId) {
      return;
    }

    let cancelled = false;
    const pollIntervalMs = hasActiveClarificationQueue ? 12000 : 30000;

    async function pollQuickWorkspace() {
      if (cancelled || document.visibilityState === "hidden" || statementBusy) {
        return;
      }
      try {
        await syncQuickWorkspace();
      } catch {
        // Keep background polling silent and let manual refresh surface errors.
      }
    }

    const intervalId = window.setInterval(() => {
      void pollQuickWorkspace();
    }, pollIntervalMs);

    function handleVisibilityChange() {
      if (document.visibilityState === "visible") {
        void pollQuickWorkspace();
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [activeTab, effectiveTelegramUserId, hasActiveClarificationQueue, statementBusy]);

  useEffect(() => {
    if (activeTab !== "quick" || !effectiveTelegramUserId || !selectedStatementId) {
      if (!selectedStatementId) {
        setSelectedStatementDetail(null);
        setStatementDetailError(null);
      }
      setStatementDetailBusy(false);
      return;
    }

    let cancelled = false;

    async function loadStatementDetail() {
      const apiBase = resolveApiBaseUrl();
      setStatementDetailBusy(true);
      setStatementDetailError(null);
      try {
        const detailUrl = buildApiUrl(apiBase, `/api/v1/statements/detail/${selectedStatementId}`, { language });
        const detail = await fetchJson<StatementDetail>(detailUrl);
        if (!cancelled) {
          setSelectedStatementDetail(detail);
        }
      } catch (detailError) {
        if (!cancelled) {
          setSelectedStatementDetail(null);
          setStatementDetailError(detailError instanceof Error ? detailError.message : "Statement detail failed.");
        }
      } finally {
        if (!cancelled) {
          setStatementDetailBusy(false);
        }
      }
    }

    void loadStatementDetail();

    return () => {
      cancelled = true;
    };
  }, [activeTab, effectiveTelegramUserId, selectedStatementId, statementHistory, language]);

  async function refreshDashboard(options?: {
    preserveOnError?: boolean;
    surfaceError?: boolean;
    showLoading?: boolean;
    statementLanguage?: Language;
  }) {
    const apiBase = resolveApiBaseUrl();
    const preserveOnError = options?.preserveOnError ?? false;
    const surfaceError = options?.surfaceError ?? true;
    const showLoading = options?.showLoading ?? true;
    const statementLanguage = options?.statementLanguage ?? language;
    if (showLoading) {
      setLoading(true);
    }
    if (surfaceError) {
      setError(null);
    }
    try {
      const microUrl = buildApiUrl(apiBase, "/api/v1/dashboard/micro");
      const statementWorkbenchUrl = effectiveTelegramUserId
        ? buildApiUrl(apiBase, "/api/v1/statements/workbench", {
            language: statementLanguage,
            limit: 6,
          })
        : null;
      const [macro, medium, micro, statementWorkbench] = await Promise.all([
        fetchJson<DashboardMacro>(`${apiBase}/api/v1/dashboard/macro`),
        fetchJson<DashboardMedium>(`${apiBase}/api/v1/dashboard/medium`),
        fetchJson<DashboardMicro>(microUrl),
        statementWorkbenchUrl
          ? fetchJson<StatementWorkbenchResponse>(statementWorkbenchUrl)
          : Promise.resolve<StatementWorkbenchResponse | null>(null),
      ]);
      setDashboard({ macro, medium, micro });
      setStatementPending(statementWorkbench?.pending ?? null);
      setStatementStatus(statementWorkbench?.latest_status ?? null);
      setStatementHistory(statementWorkbench?.history ?? []);
      if (micro.preferred_language) {
        const nextLanguage = resolveLanguage(micro.preferred_language);
        persistLanguagePreference(nextLanguage);
        setLanguage((currentLanguage) => (currentLanguage === nextLanguage ? currentLanguage : nextLanguage));
      }
    } catch (refreshError) {
      if (surfaceError) {
        setError(refreshError instanceof Error ? refreshError.message : "sync failed");
      }
      if (!preserveOnError) {
        setDashboard(buildEmptyDashboard(effectiveTelegramUserId ?? undefined));
        setStatementPending(null);
        setStatementStatus(null);
        setStatementHistory([]);
      }
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  }

  async function handleStatementStatusRefresh() {
    if (!effectiveTelegramUserId) {
      setStatementError(statementText.previewHint);
      return;
    }

    setStatementBusy(true);
    setStatementError(null);
    try {
      const quickWorkspace = await syncQuickWorkspace();
      setStatementNotice(
        quickWorkspace.workbenchResult.latest_status ? statementText.statusRefreshed : statementText.workbenchIdleBody,
      );
    } catch (statementStatusError) {
      setStatementError(statementStatusError instanceof Error ? statementStatusError.message : "Status refresh failed.");
    } finally {
      setStatementBusy(false);
    }
  }

  async function handleLanguageChange(nextLanguage: Language) {
    persistLanguagePreference(nextLanguage);
    startTransition(() => setLanguage(nextLanguage));
    setLanguageError(null);
    setLanguageNotice(null);

    if (!effectiveTelegramUserId) {
      setLanguageNotice(miniAppLanguageCopy[nextLanguage].previewSaved);
      return;
    }

    const apiBase = resolveApiBaseUrl();
    setLanguageSaving(true);
    try {
      const result = await patchJson<ProfilePreferenceResponse>(`${apiBase}/api/v1/profile/preferences`, {
        telegram_user_id: effectiveTelegramUserId,
        preferred_language: nextLanguage,
      });
      persistLanguagePreference(result.preferred_language);
      startTransition(() => setLanguage(result.preferred_language));
      setDashboard((currentDashboard) =>
        currentDashboard
          ? {
              ...currentDashboard,
              micro: {
                ...currentDashboard.micro,
                preferred_language: result.preferred_language,
              },
            }
          : currentDashboard,
      );
      setLanguageNotice(miniAppLanguageCopy[result.preferred_language].saved);
      try {
        await syncQuickWorkspace(result.preferred_language);
      } catch {
        // Keep preference saving successful even if the live statement workspace refresh lags.
      }
    } catch (preferenceError) {
      setLanguageError(
        preferenceError instanceof Error ? preferenceError.message : miniAppLanguageCopy[nextLanguage].failed,
      );
    } finally {
      setLanguageSaving(false);
    }
  }

  function applyStatementImportResult(result: StatementImportResult) {
    setStatementPending(result.pending);
    setStatementStatus(result.latest_status);
    setStatementHistory(result.history);
    setSelectedStatementId(result.imported_statement_id);
    setStatementDetailError(null);
    setStatementNotice([result.summary_message, result.prompt_message].filter(Boolean).join("\n\n"));
  }

  function refreshDashboardInBackground() {
    void refreshDashboard({ preserveOnError: true, surfaceError: false, showLoading: false });
  }

  const focusQuickWorkspace = useEffectEvent((focus: DeepLinkFocus) => {
    window.requestAnimationFrame(() => {
      const target =
        focus === "clarify"
          ? clarificationCardRef.current ?? statementImportCardRef.current
          : statementDetailCardRef.current ?? statementImportCardRef.current;
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  const handleStatementHistoryResume = useEffectEvent(async () => {
    setStatementError(null);
    setStatementNotice(statementText.historyResumeNotice);
    if (hasPendingClarification) {
      focusQuickWorkspace("clarify");
      return;
    }
    try {
      const quickWorkspace = await syncQuickWorkspace();
      setStatementNotice(
        quickWorkspace.workbenchResult.pending ? statementText.historyResumeNotice : statementText.statusRefreshed,
      );
      focusQuickWorkspace(quickWorkspace.workbenchResult.pending ? "clarify" : "statement");
    } catch (resumeError) {
      const message = resumeError instanceof Error ? resumeError.message : statementText.previewHint;
      setStatementError(message);
      setStatementNotice(null);
    }
  });

  async function handleStatementImport() {
    if (!effectiveTelegramUserId || !effectiveTelegramChatId) {
      setStatementError(statementText.previewHint);
      triggerTelegramNotification("error");
      return;
    }
    if (!statementDraft.trim()) {
      setStatementError(statementText.importFirst);
      triggerTelegramNotification("warning");
      return;
    }

    const apiBase = resolveApiBaseUrl();
    setStatementBusy(true);
    setStatementError(null);
    setStatementNotice(null);
    try {
      const result = await postJson<StatementImportResult>(`${apiBase}/api/v1/statements/import-text`, {
        telegram_user_id: effectiveTelegramUserId,
        telegram_chat_id: effectiveTelegramChatId,
        raw_text: statementDraft.trim(),
        language,
      });
      setStatementDraft("");
      setClarificationReply("");
      applyStatementImportResult(result);
      refreshDashboardInBackground();
      triggerTelegramNotification("success");
    } catch (statementImportError) {
      if (statementImportError instanceof HttpError && statementImportError.status === 409) {
        setStatementError(statementImportError.message);
        triggerTelegramNotification("warning");
        try {
          const quickWorkspace = await syncQuickWorkspace();
          focusQuickWorkspace(quickWorkspace.workbenchResult.pending ? "clarify" : "statement");
        } catch {
          // Keep the conflict detail visible even if rehydration fails.
        }
      } else {
        setStatementError(statementImportError instanceof Error ? statementImportError.message : "Statement import failed.");
        triggerTelegramNotification("error");
      }
    } finally {
      setStatementBusy(false);
    }
  }

  async function handleStatementFileUpload(file: File | null) {
    if (!file) {
      return;
    }
    if (!effectiveTelegramUserId || !effectiveTelegramChatId) {
      setStatementError(statementText.previewHint);
      triggerTelegramNotification("error");
      return;
    }

    const apiBase = resolveApiBaseUrl();
    setStatementBusy(true);
    setStatementError(null);
    setStatementNotice(null);
    try {
      const formData = new FormData();
      formData.set("telegram_user_id", String(effectiveTelegramUserId));
      formData.set("telegram_chat_id", String(effectiveTelegramChatId));
      formData.set("language", language);
      formData.set("file", file);
      const result = await postFormData<StatementImportResult>(`${apiBase}/api/v1/statements/import-file`, formData);
      setStatementDraft("");
      setClarificationReply("");
      applyStatementImportResult(result);
      refreshDashboardInBackground();
      triggerTelegramNotification("success");
    } catch (statementImportError) {
      if (statementImportError instanceof HttpError && statementImportError.status === 409) {
        setStatementError(statementImportError.message);
        triggerTelegramNotification("warning");
        try {
          const quickWorkspace = await syncQuickWorkspace();
          focusQuickWorkspace(quickWorkspace.workbenchResult.pending ? "clarify" : "statement");
        } catch {
          // Keep the conflict detail visible even if rehydration fails.
        }
      } else {
        setStatementError(statementImportError instanceof Error ? statementImportError.message : "Statement import failed.");
        triggerTelegramNotification("error");
      }
    } finally {
      setStatementBusy(false);
    }
  }

  async function handleQuickAddSubmit() {
    if (!effectiveTelegramUserId || !effectiveTelegramChatId) {
      setQuickError(quickText.previewHint);
      triggerTelegramNotification("error");
      return;
    }
    if (!quickDraft.trim()) {
      setQuickError(quickText.placeholder);
      triggerTelegramNotification("warning");
      return;
    }

    const apiBase = resolveApiBaseUrl();
    setQuickBusy(true);
    setQuickError(null);
    setQuickNotice(null);
    try {
      const normalizedDraft = quickDraft.trim();
      if (isQuickAssistantPrompt(normalizedDraft)) {
        const result = await postJson<QuickAssistantResult>(`${apiBase}/api/v1/transactions/query`, {
          question: normalizedDraft,
          telegram_user_id: effectiveTelegramUserId,
          telegram_chat_id: effectiveTelegramChatId,
        });
        setQuickDraft("");
        setQuickResult(null);
        setQuickAssistantResult(result);
        setQuickNotice(result.answer);
      } else {
        const result = await postJson<QuickAddResult>(`${apiBase}/api/v1/transactions`, {
          raw_text: normalizedDraft,
          telegram_user_id: effectiveTelegramUserId,
          telegram_chat_id: effectiveTelegramChatId,
          account_type: quickAccountType,
        });
        setQuickDraft("");
        setQuickAssistantResult(null);
        setQuickResult(result);
        setQuickNotice(result.message);
        refreshDashboardInBackground();
      }
      triggerTelegramNotification("success");
    } catch (quickAddError) {
      setQuickError(quickAddError instanceof Error ? quickAddError.message : "Quick add failed.");
      triggerTelegramNotification("error");
    } finally {
      setQuickBusy(false);
    }
  }

  async function handleReceiptUpload(file: File | null) {
    if (!file) {
      return;
    }
    if (!effectiveTelegramUserId || !effectiveTelegramChatId) {
      setQuickReceiptError(quickText.previewHint);
      triggerTelegramNotification("error");
      return;
    }

    const apiBase = resolveApiBaseUrl();
    setQuickReceiptBusy(true);
    setQuickReceiptError(null);
    setQuickReceiptNotice(null);
    try {
      const formData = new FormData();
      formData.set("telegram_user_id", String(effectiveTelegramUserId));
      formData.set("telegram_chat_id", String(effectiveTelegramChatId));
      formData.set("file", file);
      const result = await postFormData<ReceiptUploadResult>(`${apiBase}/api/v1/receipts/upload`, formData);
      setQuickReceiptNotice(result.message);
      refreshDashboardInBackground();
      triggerTelegramNotification("success");
    } catch (receiptUploadError) {
      setQuickReceiptError(
        receiptUploadError instanceof Error ? receiptUploadError.message : "Receipt upload failed.",
      );
      triggerTelegramNotification("error");
    } finally {
      setQuickReceiptBusy(false);
    }
  }

  async function handleStatementSourceDownload(target: StatementSourceTarget) {
    const apiBase = resolveApiBaseUrl();
    setStatementDownloadTargetId(target.imported_statement_id);
    setStatementError(null);
    try {
      const sourceUrl = buildApiUrl(apiBase, `/api/v1/statements/detail/${target.imported_statement_id}/source`, {
        language,
      });
      const { blob, filename } = await fetchBlob(sourceUrl);
      triggerBrowserDownload(blob, filename ?? resolveStatementSourceFilename(target));
      setStatementNotice(statementText.sourceDownloaded);
      triggerTelegramNotification("success");
    } catch (sourceError) {
      setStatementError(sourceError instanceof Error ? sourceError.message : "Statement source download failed.");
      triggerTelegramNotification("error");
    } finally {
      setStatementDownloadTargetId(null);
    }
  }

  async function handleClarificationSubmit(
    choice?: Pick<StatementQuickChoice, "account_type" | "life_sector"> | Pick<ClarificationRulePreview, "account_type" | "life_sector">,
  ) {
    if (!effectiveTelegramUserId || !effectiveTelegramChatId) {
      setStatementError(statementText.previewHint);
      triggerTelegramNotification("error");
      return;
    }
    if (!choice && !clarificationReply.trim()) {
      setStatementError(statementText.textReplyHint);
      triggerTelegramNotification("warning");
      return;
    }

    const apiBase = resolveApiBaseUrl();
    setStatementBusy(true);
    setStatementError(null);
    setStatementNotice(null);
    try {
      const result = await postJson<StatementClarificationResult>(`${apiBase}/api/v1/statements/clarify`, {
        telegram_user_id: effectiveTelegramUserId,
        telegram_chat_id: effectiveTelegramChatId,
        answer_text: choice ? null : clarificationReply.trim(),
        account_type: choice?.account_type ?? null,
        life_sector: choice?.life_sector ?? null,
        language,
      });
      setClarificationReply("");
      setStatementPending(result.pending);
      setStatementStatus(result.latest_status);
      setStatementHistory(result.history);
      setStatementNotice(result.message);
      refreshDashboardInBackground();
      triggerTelegramNotification("success");
    } catch (clarificationError) {
      if (clarificationError instanceof HttpError && clarificationError.status === 404) {
        try {
          const quickWorkspace = await syncQuickWorkspace();
          setClarificationReply("");
          focusQuickWorkspace(quickWorkspace.workbenchResult.pending ? "clarify" : "statement");
          setStatementNotice(
            quickWorkspace.workbenchResult.pending ? statementText.statusRefreshed : clarificationError.message,
          );
          triggerTelegramNotification("warning");
        } catch {
          setStatementError(clarificationError.message);
          triggerTelegramNotification("error");
        }
      } else {
        setStatementError(clarificationError instanceof Error ? clarificationError.message : "Clarification failed.");
        triggerTelegramNotification("error");
      }
    } finally {
      setStatementBusy(false);
    }
  }

  const macro = deferredDashboard?.macro ?? buildEmptyDashboard(effectiveTelegramUserId ?? undefined).macro;
  const medium = deferredDashboard?.medium ?? buildEmptyDashboard(effectiveTelegramUserId ?? undefined).medium;
  const micro = deferredDashboard?.micro ?? buildEmptyDashboard(effectiveTelegramUserId ?? undefined).micro;
  const locale = localeByLanguage(language);
  const safeAmount = asNumber(medium.safe_to_withdraw.safe_amount);
  const availableBusinessBalance = Math.max(asNumber(medium.safe_to_withdraw.available_business_balance), 1);
  const projectedReturn = sandboxResult?.scorecard.projected_return_amount ?? String(Math.round(investment * (1 + roi / 100)));
  const cashPressure = sandboxResult?.scorecard.cash_pressure_pct ?? String(Math.min(100, Math.round((investment / availableBusinessBalance) * 100)));
  const paybackDays = sandboxResult?.scorecard.payback_days ?? Math.max(7, Math.round(45 - roi / 4));
  const clarificationCardState = getClarificationCardState(statementPending, micro.pending_clarification);
  const currentStatementItem = clarificationCardState?.item ?? null;
  const clarificationQueuePreview = buildClarificationQueuePreview(statementPending, micro.pending_clarification);
  const prioritizedQuickChoices = prioritizeStatementQuickChoices(statementQuickChoices, currentStatementItem);
  const primaryLearnedRule = currentStatementItem?.matched_rules[0] ?? null;
  const clarificationResolvedCount = clarificationCardState?.resolvedCount ?? 0;
  const clarificationRemainingCount = clarificationCardState?.remainingCount ?? 0;
  const clarificationTotalCount =
    clarificationCardState?.totalCount ?? clarificationResolvedCount + clarificationRemainingCount;
  const clarificationProgressValue =
    clarificationTotalCount > 0 ? Math.min(100, Math.round((clarificationResolvedCount / clarificationTotalCount) * 100)) : 0;
  const selectedDetailPending = selectedStatementDetail?.pending ?? null;
  const selectedDetailClarificationState = getClarificationCardState(selectedDetailPending, null);
  const selectedDetailItem = selectedDetailClarificationState?.item ?? null;
  const selectedDetailQueuePreview = buildClarificationQueuePreview(selectedDetailPending, null);
  const selectedDetailPrioritizedQuickChoices = prioritizeStatementQuickChoices(statementQuickChoices, selectedDetailItem);
  const selectedDetailPrimaryLearnedRule = selectedDetailItem?.matched_rules[0] ?? null;
  const selectedDetailResolvedCount = selectedDetailClarificationState?.resolvedCount ?? 0;
  const selectedDetailRemainingCount =
    selectedDetailClarificationState?.remainingCount ?? selectedStatementDetail?.remaining_clarifications ?? 0;
  const selectedDetailTotalCount =
    selectedDetailClarificationState?.totalCount ?? selectedDetailResolvedCount + selectedDetailRemainingCount;
  const selectedDetailProgressValue =
    selectedDetailTotalCount > 0 ? Math.min(100, Math.round((selectedDetailResolvedCount / selectedDetailTotalCount) * 100)) : 0;
  const statementDownloadBusy = statementDownloadTargetId !== null;
  const canDownloadSelectedStatementSource = selectedStatementDetail ? canDownloadStatementSource(selectedStatementDetail) : false;
  const sandboxRunwayLabel = sandboxResult ? formatRunwayLabel(sandboxResult.scorecard.runway_label, sandboxText) : null;
  const sandboxVerdictLabel = sandboxResult ? formatVerdict(sandboxResult.scorecard.verdict, sandboxText) : null;
  const apiBaseUrl = resolveApiBaseUrl();
  const quickAddEndpointUrl = buildAbsoluteUrl(apiBaseUrl, micro.quick_add_path);
  const webAppUrl = buildAbsoluteUrl(window.location.origin, micro.webapp_url);
  const hasPendingClarification = Boolean(clarificationCardState);
  const activeStatementImportId =
    clarificationCardState?.statementId ??
    (statementStatus?.remaining_clarifications ? statementStatus.imported_statement_id : null);
  const shortcutHeaderSample = JSON.stringify(
    {
      "Content-Type": "application/json",
      "X-API-KEY": "<LOCAL_SHORTCUT_API_KEY>",
    },
    null,
    2,
  );

  useEffect(() => {
    if (activeTab !== "quick") {
      return;
    }

    const focus = deepLinkFocusRef.current;
    if (!focus) {
      return;
    }

    let target: HTMLElement | null = null;
    if (focus === "clarify") {
      if (!hasPendingClarification) {
        target = statementImportCardRef.current;
      } else {
        target = clarificationCardRef.current ?? statementImportCardRef.current;
      }
    } else if (focus === "statement") {
      if (selectedStatementId && !statementDetailCardRef.current && !statementDetailError) {
        return;
      }
      target = statementDetailCardRef.current ?? statementImportCardRef.current;
    }

    if (!target) {
      return;
    }

    target.scrollIntoView({ behavior: "smooth", block: "start" });
    consumeInitialFocus();
    deepLinkFocusRef.current = null;
  }, [activeTab, hasPendingClarification, selectedStatementId, statementDetailError]);
  const shortcutPayloadSample = JSON.stringify(
    effectiveTelegramUserId && effectiveTelegramChatId
      ? {
          raw_text: "+150000 avans",
          telegram_user_id: effectiveTelegramUserId,
          telegram_chat_id: effectiveTelegramChatId,
          account_type: "business",
        }
      : {
          raw_text: "+150000 avans",
          account_type: "business",
        },
    null,
    2,
  );
  const shortcutCurlSample = [
    `curl -X POST "${quickAddEndpointUrl}" \\`,
    '  -H "Content-Type: application/json" \\',
    '  -H "X-API-KEY: <LOCAL_SHORTCUT_API_KEY>" \\',
    "  -d '{\"raw_text\":\"+150000 avans\",\"account_type\":\"business\"}'",
  ].join("\n");
  const qalSignals = [
    {
      label: text.onboarding,
      value: micro.onboarding_completed ? text.complete : text.pending,
      ready: Boolean(micro.onboarding_completed),
    },
    {
      label: text.statements,
      value: `${macro.imported_statements_total} / ${macro.clarification_open_total}`,
      ready: macro.imported_statements_total > 0 && macro.clarification_open_total === 0,
    },
    {
      label: cashierText.receiptsWindow,
      value: `${medium.recent_receipts_total} / ${medium.tracked_skus_total}`,
      ready: medium.recent_receipts_total > 0 && medium.tracked_skus_total > 0,
    },
    {
      label: text.safeToWithdraw,
      value: formatMoney(medium.safe_to_withdraw.safe_amount, locale),
      ready: asNumber(medium.safe_to_withdraw.safe_amount) > 0,
    },
  ];
  const qalActiveSignals = qalSignals.filter((signal) => signal.ready).length;
  const qalPreviewScore = Math.max(
    12,
    Math.min(
      100,
      24 +
        qalActiveSignals * 16 +
        Math.min(macro.imported_statements_total, 6) * 4 +
        Math.min(medium.tracked_skus_total, 10) * 2 -
        Math.min(macro.clarification_open_total, 4) * 8,
    ),
  );
  const qalMintWindow = Math.max(
    0,
    qalActiveSignals * 3 + macro.imported_statements_total + medium.recent_receipts_total - macro.clarification_open_total * 4,
  );
  const qalStatusLabel =
    macro.clarification_open_total > 0
      ? text.settingsQalHold
      : qalMintWindow > 0
        ? text.settingsQalEligible
        : text.settingsQalBooting;
  const marketCards: SettingsMarketCard[] = [
    {
      title: text.settingsMarketClarificationsTitle,
      body:
        macro.clarification_open_total > 0
          ? text.settingsMarketClarificationsOpen
          : text.settingsMarketClarificationsClear,
      badge: macro.clarification_open_total > 0 ? text.settingsMarketNow : text.settingsMarketNext,
      tone: macro.clarification_open_total > 0 ? "urgent" : "planned",
    },
    {
      title: text.settingsMarketReceiptsTitle,
      body:
        medium.recent_receipts_total > 0
          ? text.settingsMarketReceiptsReady
          : text.settingsMarketReceiptsMissing,
      badge: medium.recent_receipts_total > 0 ? text.settingsMarketNext : text.settingsMarketNow,
      tone: medium.recent_receipts_total > 0 ? "support" : "watch",
    },
    {
      title: text.settingsMarketRunwayTitle,
      body:
        medium.safe_to_withdraw.projected_gap_date || medium.gap_scenarios.length > 0
          ? text.settingsMarketRunwayGap
          : text.settingsMarketRunwayStable,
      badge:
        medium.safe_to_withdraw.projected_gap_date || medium.gap_scenarios.length > 0
          ? text.settingsMarketNow
          : text.settingsMarketWatch,
      tone: medium.safe_to_withdraw.projected_gap_date || medium.gap_scenarios.length > 0 ? "urgent" : "planned",
    },
    {
      title: text.settingsMarketShortcutsTitle,
      body: text.settingsMarketShortcutsBody,
      badge: effectiveTelegramUserId ? text.settingsMarketNext : text.settingsMarketWatch,
      tone: effectiveTelegramUserId ? "support" : "watch",
    },
  ];
  const activeTabMeta = tabs.find((tab) => tab.id === activeTab) ?? tabs[0];
  const sceneTab = quickSheetOpen ? lastNonQuickTabRef.current : activeTab;
  const sceneTabMeta = tabs.find((tab) => tab.id === sceneTab) ?? tabs[0];
  const bankCards = [
    {
      id: "kaspi",
      title: "Kaspi Flow",
      subtitle: formatAccountType("business", languageText),
      amount: formatMoney(macro.business_balance, locale),
      tone: "sunrise" as const,
    },
    {
      id: "halyk",
      title: "Halyk Reserve",
      subtitle: formatAccountType("personal", languageText),
      amount: formatMoney(macro.personal_balance, locale),
      tone: "mint" as const,
    },
    {
      id: "qaltam",
      title: "Qaltam Buffer",
      subtitle: text.safeToWithdraw,
      amount: formatMoney(medium.safe_to_withdraw.reserve_buffer, locale),
      tone: "ocean" as const,
    },
  ];
  const sandboxProbability = sandboxResult
    ? Math.max(0, Math.min(100, asNumber(sandboxResult.scorecard.probability_of_success)))
    : Math.max(0, Math.min(100, Math.round((roi * 0.7 + (60 - lagDays) * 0.8) / 1.4)));
  const activeIssuesCount = macro.clarification_open_total + (statementPending?.remaining_count ?? 0);
  const balanceStatusClass = activeIssuesCount > 0 ? "balance-status warning" : "balance-status ready";
  const shellStatusMessage = error || languageError;
  const shellStatusText = error ? text.syncIssue : languageError;
  const shellStatusTone = error || languageError ? "status-banner error" : "status-banner";
  const handleQuickSheetDragEnd = (_event: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
    if (info.offset.y > 120 || info.velocity.y > 720) {
      triggerTelegramImpact("soft");
      closeQuickSheet();
    }
  };

  return (
    <main className="app-shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />
      <div className="app-frame">
        <header className="app-topbar">
          <button
            className="app-brand app-brand-button"
            type="button"
            data-testid="header-summary-toggle"
            aria-expanded={summarySheetOpen}
            onClick={() => {
              toggleSummarySheet();
            }}
          >
            <span className="app-kicker">QALTAM Mini App</span>
            <h1>{sceneTabMeta.label[language]}</h1>
            <p>{formatDate(macro.as_of, locale)}</p>
          </button>
          <button
            className="ghost-button topbar-action"
            type="button"
            onClick={() => {
              void refreshDashboard();
            }}
          >
            {loading ? text.syncing : text.sync}
          </button>
        </header>

        {shellStatusMessage ? <div className={shellStatusTone}>{shellStatusText}</div> : null}

        <section className="tab-content">
          <AnimatePresence mode="wait">
            <motion.section
              key={sceneTab}
              className="tab-scene"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.24, ease: "easeOut" }}
            >
          {sceneTab === "map" ? (
            <div className="page-grid" data-testid="scene-map">
              <button
                type="button"
                className="home-summary-card"
                data-testid="home-summary-card"
                onClick={() => {
                  toggleSummarySheet();
                }}
              >
                <div className="home-summary-copy">
                  <span className="balance-card-label">{text.balance}</span>
                  <strong className="balance-card-value" data-testid="balance-total">
                    {formatMoney(macro.total_balance, locale)}
                  </strong>
                </div>
                <div className={balanceStatusClass}>
                  <span>{activeIssuesCount > 0 ? text.clarifications : text.complete}</span>
                  <strong>{activeIssuesCount > 0 ? String(activeIssuesCount) : text.settingsQalEligible}</strong>
                </div>
              </button>
              <Panel title={text.bridges} subtitle={text.mapLead}>
                <BridgeOrbit bridges={macro.bridge_totals} locale={locale} flowLabel={languageText.flowItems} />
              </Panel>
              <Panel title={text.accountMix} subtitle={text.mapLead}>
                <div className="account-list">
                  {macro.account_balances.map((account) => (
                    <div key={`${account.account_type}-${account.label}`} className="account-row">
                      <div>
                        <strong>{account.label}</strong>
                        <span>{formatAccountType(account.account_type, languageText)}</span>
                      </div>
                      <strong>{formatMoney(account.balance, locale)}</strong>
                    </div>
                  ))}
                </div>
                <div className="pill-row">
                  <InfoPill label={text.income30} value={formatMoney(macro.monthly_income, locale)} />
                  <InfoPill label={text.expense30} value={formatMoney(macro.monthly_expense, locale)} />
                  <InfoPill label={text.statements} value={String(macro.imported_statements_total)} />
                </div>
              </Panel>
            </div>
          ) : null}

          {sceneTab === "cashier" ? (
            <div className="page-grid" data-testid="scene-cashier">
              <Panel title={text.safeToWithdraw} subtitle={text.projection}>
                <div className="cashier-safe-card">
                  <span className="balance-card-label">{text.safeToWithdraw}</span>
                  <div className="highlight-number">{formatMoney(medium.safe_to_withdraw.safe_amount, locale)}</div>
                  <p className="helper-note">{text.projection}</p>
                </div>
                <div className="pill-row">
                  <InfoPill label={text.reserve} value={formatMoney(medium.safe_to_withdraw.reserve_buffer, locale)} />
                  <InfoPill label={text.obligations} value={formatMoney(medium.obligations_total, locale)} />
                  <InfoPill
                    label={text.gap}
                    value={
                      medium.safe_to_withdraw.projected_gap_date
                        ? formatDate(medium.safe_to_withdraw.projected_gap_date, locale)
                        : cashierText.stable
                    }
                  />
                </div>
                <ProjectionChart points={medium.projection} locale={locale} />
                <BankCardRail cards={bankCards} />
                <div className="pill-row receipt-pills">
                  <InfoPill label={cashierText.receiptsWindow} value={String(medium.recent_receipts_total)} />
                  <InfoPill label={cashierText.receiptSpend} value={formatMoney(medium.recent_receipts_amount, locale)} />
                  <InfoPill label={cashierText.trackedSkus} value={String(medium.tracked_skus_total)} />
                </div>
              </Panel>
              <Panel title={cashierText.receiptLane} subtitle={cashierText.receiptBody}>
                <div className="section-stack">
                  <div className="cashflow-ledger">
                    <div className="cashflow-ledger-row">
                      <span>{text.income30}</span>
                      <strong>{formatMoney(macro.monthly_income, locale)}</strong>
                    </div>
                    <div className="cashflow-ledger-row">
                      <span>{text.expense30}</span>
                      <strong>{formatMoney(macro.monthly_expense, locale)}</strong>
                    </div>
                  </div>
                  {medium.last_receipt ? (
                    <article className="receipt-card">
                      <div className="receipt-top">
                        <div>
                          <strong>{medium.last_receipt.merchant_name ?? languageText.receiptFallback}</strong>
                          <span>
                            {formatDate(medium.last_receipt.purchased_at, locale)} · {medium.last_receipt.parsed_status}
                          </span>
                        </div>
                        <strong>{formatMoney(medium.last_receipt.total_amount, locale)}</strong>
                      </div>
                      <div className="receipt-items">
                        {medium.last_receipt.items.slice(0, 4).map((item) => (
                          <div key={`${medium.last_receipt?.id}-${item.sku_name}`} className="receipt-item-row">
                            <div>
                              <strong>{item.sku_name}</strong>
                              <span>
                                {item.category} · x{formatCount(item.quantity, locale)}
                              </span>
                            </div>
                            <strong>{formatMoney(item.total_price, locale)}</strong>
                          </div>
                        ))}
                      </div>
                    </article>
                  ) : (
                    <div className="empty-state">{cashierText.noReceiptHistory}</div>
                  )}

                  <div className="section-divider">
                    <strong>{cashierText.inflationTracker}</strong>
                  </div>
                  {medium.inflation_leaders.length ? (
                    <div className="inflation-list">
                      {medium.inflation_leaders.slice(0, 6).map((item) => (
                        <article key={item.sku_key} className="inflation-row">
                          <div>
                            <strong>{item.sku_name}</strong>
                            <span>
                              {(item.merchant_name ?? item.category) || item.category} ·{" "}
                              {formatDate(item.latest_seen_at, locale)}
                            </span>
                          </div>
                          <div className="inflation-values">
                            <strong>{formatMoney(item.latest_price, locale)}</strong>
                            <span>
                              {item.previous_price && item.price_change_pct
                                ? `${cashierText.previousPrice} ${formatMoney(item.previous_price, locale)} · ${formatSignedPercent(item.price_change_pct, locale)}`
                                : cashierText.stable}
                            </span>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-state">{cashierText.noInflation}</div>
                  )}

                  <div className="section-divider">
                    <strong>{cashierText.flowAndActions}</strong>
                  </div>
                  <div className="scenario-list">
                    {medium.gap_scenarios.slice(0, 4).map((scenario) => (
                      <article key={scenario.order} className="scenario-card">
                        <div className="scenario-head">
                          <strong>{scenario.title}</strong>
                          <span className={scenario.urgency === "urgent" ? "tag urgent" : "tag planned"}>
                            {scenario.urgency}
                          </span>
                        </div>
                        <p>{scenario.action}</p>
                        <small>
                          {cashierText.priceJump}: {formatMoney(scenario.estimated_impact, locale)}
                        </small>
                      </article>
                    ))}
                  </div>
                </div>
                <div className="transaction-list">
                  {medium.recent_transactions.length ? (
                    medium.recent_transactions.map((transaction) => (
                      <div key={transaction.id} className="transaction-row">
                        <div>
                          <strong>{transaction.category}</strong>
                          <span>{formatDate(transaction.created_at, locale)} · {transaction.account_name}</span>
                        </div>
                        <strong className={transaction.transaction_type === "income" ? "amount-positive" : "amount-negative"}>
                          {transaction.transaction_type === "income" ? "+" : "-"}
                          {formatMoney(transaction.amount, locale)}
                        </strong>
                      </div>
                    ))
                  ) : (
                    <div className="empty-state">{text.noTransactions}</div>
                  )}
                </div>
              </Panel>
            </div>
          ) : null}

          {createPortal(
            <AnimatePresence>
              {quickSheetOpen ? (
                <motion.div
                  className="quick-sheet-screen"
                  data-testid="scene-quick"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2, ease: "easeOut" }}
                  onClick={() => {
                    triggerTelegramImpact("soft");
                    closeQuickSheet();
                  }}
                >
                  <motion.div
                    className="quick-sheet-shell"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="quick-sheet-title"
                    initial={{ y: 88, opacity: 0.92, scale: 0.985 }}
                    animate={{ y: 0, opacity: 1, scale: 1 }}
                    exit={{ y: 120, opacity: 0.88, scale: 0.985 }}
                    transition={{ type: "spring", stiffness: 280, damping: 28, mass: 0.92 }}
                    drag="y"
                    dragListener={false}
                    dragControls={quickSheetDragControls}
                    dragConstraints={{ top: 0, bottom: 0 }}
                    dragElastic={{ top: 0, bottom: 0.22 }}
                    onDragEnd={handleQuickSheetDragEnd}
                    onClick={(event) => {
                      event.stopPropagation();
                    }}
                  >
                    <div
                      className="quick-sheet-dragger"
                      aria-hidden="true"
                      onPointerDown={(event) => {
                        quickSheetDragControls.start(event);
                      }}
                    >
                      <span className="quick-sheet-handle" />
                    </div>
                    <Panel
                      title={quickText.title}
                      subtitle={quickText.heroKicker}
                      titleId="quick-sheet-title"
                      className="quick-sheet-panel"
                    >
                      <div className="section-stack">
                        <article className="quick-sheet-hero">
                          <div className="quick-sheet-head">
                            <span className="tag support">{quickText.heroKicker}</span>
                            <button
                              type="button"
                              data-testid="quick-close"
                              className="ghost-button quick-sheet-close"
                              onClick={() => {
                                triggerTelegramImpact("soft");
                                closeQuickSheet();
                              }}
                            >
                              {quickText.closeAction}
                            </button>
                          </div>
                          <VoiceWave />
                          <div className="quick-sheet-glow">
                            <span>{quickText.placeholder}</span>
                            <strong>{quickExamples.expense}</strong>
                          </div>
                        </article>
                        <article className="statement-input-card" ref={statementImportCardRef}>
                          <div className="clarification-top">
                            <strong>{quickText.heroKicker}</strong>
                            <span className="tag planned">{formatAccountType(quickAccountType, languageText)}</span>
                          </div>
                    <p>{quickText.body}</p>
                    <textarea
                      data-testid="quick-draft-input"
                      className="statement-textarea compact"
                      value={quickDraft}
                      onChange={(event) => setQuickDraft(event.target.value)}
                      placeholder={quickText.placeholder}
                    />
                    <div className="pill-row quick-account-row">
                      <span className="helper-note">{quickText.accountTitle}</span>
                      <button
                        type="button"
                        data-testid="quick-account-business"
                        className={quickAccountType === "business" ? "language-pill active" : "language-pill"}
                        onClick={() => {
                          triggerTelegramSelectionHaptic();
                          setQuickAccountType("business");
                        }}
                      >
                        {quickText.accountBusiness}
                      </button>
                      <button
                        type="button"
                        data-testid="quick-account-personal"
                        className={quickAccountType === "personal" ? "language-pill active" : "language-pill"}
                        onClick={() => {
                          triggerTelegramSelectionHaptic();
                          setQuickAccountType("personal");
                        }}
                      >
                        {quickText.accountPersonal}
                      </button>
                    </div>
                    <div className="helper-note">
                      {effectiveTelegramUserId
                        ? `${statementText.activeUser} ${effectiveTelegramUserId}`
                        : quickText.previewHint}
                    </div>
                    <div className="section-divider">
                      <strong>{quickText.receiptTitle}</strong>
                    </div>
                    <p className="helper-note">{quickText.receiptBody}</p>
                    <label className={quickReceiptBusy ? "upload-button disabled" : "upload-button"}>
                      <input
                        type="file"
                        accept="image/jpeg,image/png,image/webp,image/heic"
                        disabled={quickReceiptBusy}
                        onChange={(event) => {
                          const file = event.target.files?.[0] ?? null;
                          void handleReceiptUpload(file);
                          event.currentTarget.value = "";
                        }}
                      />
                      <span>{quickReceiptBusy ? quickText.receiptBusy : quickText.receiptCta}</span>
                    </label>
                    <div className="helper-note">{quickText.receiptHint}</div>
                    <div className="button-row">
                      <button
                        type="button"
                        data-testid="quick-submit"
                        className="primary-button"
                        disabled={quickBusy || quickReceiptBusy}
                        onClick={() => {
                          void handleQuickAddSubmit();
                        }}
                      >
                        {quickBusy ? quickText.submitBusy : quickText.submit}
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={quickBusy || quickReceiptBusy}
                        onClick={() => {
                          setQuickError(null);
                          setQuickNotice(null);
                          setQuickDraft(quickExamples.income);
                          setQuickAccountType("business");
                        }}
                      >
                        {quickText.loadIncome}
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={quickBusy || quickReceiptBusy}
                        onClick={() => {
                          setQuickError(null);
                          setQuickNotice(null);
                          setQuickDraft(quickExamples.expense);
                          setQuickAccountType("business");
                        }}
                      >
                        {quickText.loadExpense}
                      </button>
                    </div>
                    <div className="section-divider">
                      <strong>{quickText.samplesTitle}</strong>
                    </div>
                    <div className="quick-choice-grid">
                      {Object.values(quickExamples).map((sample) => (
                        <button
                          key={sample}
                          type="button"
                          className="ghost-button quick-choice-button"
                          disabled={quickBusy || quickReceiptBusy}
                          onClick={() => {
                            setQuickError(null);
                            setQuickDraft(sample);
                          }}
                        >
                          {sample}
                        </button>
                      ))}
                    </div>
                    {quickAssistantResult ? (
                      <div className="quick-result-card" data-testid="quick-assistant-result">
                        <div className="clarification-top">
                          <strong>{quickText.assistantTitle}</strong>
                          <span className="tag planned">AI</span>
                        </div>
                        <div className="import-card quick-result-grid">
                          <div>
                            <strong>{quickAssistantResult.answer}</strong>
                            <span>{formatMoney(quickAssistantResult.total_amount, locale)}</span>
                          </div>
                          <div>
                            <strong>{text.transactions}</strong>
                            <span>{String(quickAssistantResult.transaction_count)}</span>
                          </div>
                          <div>
                            <strong>{quickText.routeLabel}</strong>
                            <span>{quickAssistantResult.route}</span>
                          </div>
                        </div>
                        <div className="helper-note">
                          {quickAssistantResult.matched_categories.length
                            ? quickAssistantResult.matched_categories.join(", ")
                            : quickAssistantResult.source}
                        </div>
                      </div>
                    ) : null}
                    {quickResult ? (
                      <div className="quick-result-card" data-testid="quick-transaction-result">
                        <div className="clarification-top">
                          <strong>{quickText.resultTitle}</strong>
                          <span className={quickResult.transaction.type === "income" ? "tag planned" : "tag urgent"}>
                            {formatTransactionType(quickResult.transaction.type, language)}
                          </span>
                        </div>
                        <div className="import-card quick-result-grid">
                          <div>
                            <strong>{quickResult.transaction.category}</strong>
                            <span>{formatMoney(quickResult.transaction.amount, locale)}</span>
                          </div>
                          <div>
                            <strong>{formatAccountType(quickAccountType, languageText)}</strong>
                            <span>{formatDate(quickResult.transaction.created_at, locale)}</span>
                          </div>
                          <div>
                            <strong>{quickText.routeLabel}</strong>
                            <span>{quickResult.route}</span>
                          </div>
                        </div>
                        <div className="helper-note">{quickResult.normalized_text}</div>
                      </div>
                    ) : null}
                    {medium.last_receipt ? (
                      <div className="quick-result-card">
                        <div className="clarification-top">
                          <strong>{quickText.receiptReady}</strong>
                          <span className="tag planned">
                            {formatStatementParseStatus(medium.last_receipt.parsed_status, languageText)}
                          </span>
                        </div>
                        <div className="import-card quick-result-grid">
                          <div>
                            <strong>{medium.last_receipt.merchant_name ?? "Receipt"}</strong>
                            <span>{formatMoney(medium.last_receipt.total_amount, locale)}</span>
                          </div>
                          <div>
                            <strong>{medium.last_receipt.items.length} SKU</strong>
                            <span>{formatDate(medium.last_receipt.purchased_at, locale)}</span>
                          </div>
                          <div>
                            <strong>{cashierText.receiptLane}</strong>
                            <span>{medium.last_receipt.currency}</span>
                          </div>
                        </div>
                        <div className="receipt-items quick-receipt-items">
                          {medium.last_receipt.items.slice(0, 3).map((item) => (
                            <div key={`quick-${medium.last_receipt?.id}-${item.sku_name}`} className="receipt-item-row">
                              <div>
                                <strong>{item.sku_name}</strong>
                                <span>
                                  {item.category} В· x{formatCount(item.quantity, locale)}
                                </span>
                              </div>
                              <strong>{formatMoney(item.total_price, locale)}</strong>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </article>

                  {quickError ? <div className="inline-status error">{quickError}</div> : null}
                  {quickNotice ? <div className="inline-status">{quickNotice}</div> : null}
                  {quickReceiptError ? <div className="inline-status error">{quickReceiptError}</div> : null}
                  {quickReceiptNotice ? <div className="inline-status">{quickReceiptNotice}</div> : null}

                  <article className="statement-input-card">
                    <div className="clarification-top">
                      <strong>{statementText.importTitle}</strong>
                      <span className="tag planned">{effectiveTelegramUserId ? "live" : "telegram"}</span>
                    </div>
                    <p>{statementText.importBody}</p>
                    <textarea
                      className="statement-textarea"
                      value={statementDraft}
                      onChange={(event) => setStatementDraft(event.target.value)}
                      placeholder={statementText.draftPlaceholder}
                    />
                    <div className="helper-note">
                      {effectiveTelegramUserId
                        ? `${statementText.activeUser} ${effectiveTelegramUserId}`
                        : statementText.previewHint}
                    </div>
                    <label className={statementBusy ? "upload-button disabled" : "upload-button"}>
                      <input
                        type="file"
                        accept=".pdf,.csv,.xlsx,.xls,application/pdf,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
                        disabled={statementBusy}
                        onChange={(event) => {
                          const file = event.target.files?.[0] ?? null;
                          void handleStatementFileUpload(file);
                          event.currentTarget.value = "";
                        }}
                      />
                      <span>{statementBusy ? statementText.uploadBusy : statementText.uploadAction}</span>
                    </label>
                    <div className="helper-note">{statementText.uploadHint}</div>
                    <div className="button-row">
                      <button
                        type="button"
                        className="primary-button"
                        disabled={statementBusy}
                        onClick={() => {
                          void handleStatementImport();
                        }}
                      >
                        {statementBusy ? statementText.importBusy : statementText.importAction}
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={statementBusy}
                        onClick={() => {
                          setStatementError(null);
                          setStatementNotice(statementText.sampleLoaded);
                          setStatementDraft(buildSampleStatementText());
                        }}
                      >
                        {statementText.sampleAction}
                      </button>
                    </div>
                  </article>

                  {statementError ? <div className="inline-status error">{statementError}</div> : null}
                  {statementNotice ? <div className="inline-status">{statementNotice}</div> : null}

                  {statementStatus ? (
                    <article className="statement-status-card">
                      <div className="clarification-top">
                        <strong>{statementText.statusTitle}</strong>
                        <span className={statementStatus.remaining_clarifications > 0 ? "tag urgent" : "tag planned"}>
                          {formatStatementParseStatus(statementStatus.parse_status, languageText)}
                        </span>
                      </div>
                      <p>{statementText.statusBody}</p>
                      <div className="statement-status-grid">
                        <div>
                          <strong>{text.source}</strong>
                          <span>{statementStatus.source_name}</span>
                        </div>
                        <div>
                          <strong>{text.status}</strong>
                          <span>{formatStatementParseStatus(statementStatus.parse_status, languageText)}</span>
                        </div>
                        <div>
                          <strong>{languageText.fileLabel}</strong>
                          <span>{statementStatus.original_filename ?? "telegram_text_statement"}</span>
                        </div>
                        <div>
                          <strong>{statementText.importedLabel}</strong>
                          <span>{statementStatus.imported_at}</span>
                        </div>
                        <div>
                          <strong>{statementText.parsedLabel}</strong>
                          <span>{String(statementStatus.parsed_count ?? 0)}</span>
                        </div>
                        <div>
                          <strong>{statementText.autoLabel}</strong>
                          <span>{String(statementStatus.auto_count ?? 0)}</span>
                        </div>
                        <div>
                          <strong>{statementText.openLabel}</strong>
                          <span>{String(statementStatus.remaining_clarifications)}</span>
                        </div>
                      </div>
                      <div className="button-row">
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={statementBusy}
                          onClick={() => {
                            void handleStatementStatusRefresh();
                          }}
                        >
                          {statementText.refreshAction}
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={statementDownloadBusy}
                          onClick={() => {
                            void handleStatementSourceDownload(statementStatus);
                          }}
                        >
                          {statementDownloadTargetId === statementStatus.imported_statement_id
                            ? statementText.sourceDownloadBusy
                            : statementText.sourceDownloadAction}
                        </button>
                        <button type="button" className="ghost-button" onClick={openTelegramThread}>
                          {text.openBot}
                        </button>
                      </div>
                    </article>
                  ) : null}

                  {clarificationCardState ? (
                    <article className="clarification-card" ref={clarificationCardRef}>
                      <div className="clarification-top">
                        <span className="tag urgent">{text.pendingClarification}</span>
                        <strong>{clarificationRemainingCount} {languageText.leftLabel}</strong>
                      </div>
                      <div className="statement-progress-card">
                        <div className="statement-progress-top">
                          <strong>
                            {clarificationResolvedCount} / {clarificationTotalCount}
                          </strong>
                          <span>{clarificationProgressValue}%</span>
                        </div>
                        <div className="statement-progress-track" aria-hidden="true">
                          <span style={{ width: `${clarificationProgressValue}%` }} />
                        </div>
                        <div className="statement-progress-grid">
                          <div>
                            <strong>{statementText.parsedLabel}</strong>
                            <span>{String(statementPending?.parsed_count ?? statementStatus?.parsed_count ?? 0)}</span>
                          </div>
                          <div>
                            <strong>{statementText.autoLabel}</strong>
                            <span>{String(statementPending?.auto_count ?? statementStatus?.auto_count ?? 0)}</span>
                          </div>
                          <div>
                            <strong>{text.status}</strong>
                            <span>{formatTransactionType(currentStatementItem.transaction_type, language)}</span>
                          </div>
                          <div>
                            <strong>{statementText.openLabel}</strong>
                            <span>{String(clarificationRemainingCount)}</span>
                          </div>
                        </div>
                      </div>
                      <h3>
                        {formatMoney(currentStatementItem.amount, locale)} · {currentStatementItem.counterparty}
                      </h3>
                      <p>{currentStatementItem.reason}</p>
                      <div className="statement-status-grid clarification-context-grid">
                        <div>
                          <strong>{statementText.importedLabel}</strong>
                          <span>{formatDate(currentStatementItem.statement_date, locale)}</span>
                        </div>
                        <div>
                          <strong>{text.status}</strong>
                          <span>{formatTransactionType(currentStatementItem.transaction_type, language)}</span>
                        </div>
                        <div>
                          <strong>{text.source}</strong>
                          <span>{currentStatementItem.counterparty}</span>
                        </div>
                        <div>
                          <strong>{statementText.quickChoices}</strong>
                          <span>
                            {currentStatementItem.suggested_account_type || currentStatementItem.suggested_life_sector
                              ? resolveStatementSuggestionLabel(currentStatementItem, language, languageText)
                              : statementText.livePrompt}
                          </span>
                        </div>
                      </div>
                      {clarificationQueuePreview.length ? (
                        <>
                          <div className="section-divider">
                            <strong>{statementText.openLabel}</strong>
                            <span>{clarificationQueuePreview.length} {languageText.flowItems}</span>
                          </div>
                          <div className="statement-queue-list">
                            {clarificationQueuePreview.map(({ item, active }) => {
                              const queueSuggestion = resolveStatementSuggestionLabel(item, language, languageText);
                              return (
                                <article
                                  key={`${item.index}:${item.statement_date}:${item.counterparty}:${item.amount}`}
                                  className={active ? "statement-queue-card active" : "statement-queue-card"}
                                >
                                  <div className="statement-queue-top">
                                    <span className={active ? "tag urgent" : "tag planned"}>
                                      {active ? statementText.livePrompt : formatDate(item.statement_date, locale)}
                                    </span>
                                    <strong>{formatMoney(item.amount, locale)}</strong>
                                  </div>
                                  <strong>{item.counterparty}</strong>
                                  <div className="statement-queue-meta">
                                    <span>{formatTransactionType(item.transaction_type, language)}</span>
                                    <span>{queueSuggestion ?? item.reason}</span>
                                  </div>
                                </article>
                              );
                            })}
                          </div>
                        </>
                      ) : null}
                      <p className="clarification-meta">
                        {formatDate(currentStatementItem.statement_date, locale)} · {currentStatementItem.description}
                      </p>
                      <p className="clarification-hint">
                        {clarificationCardState.promptMessage || statementText.livePrompt}
                      </p>
                      {primaryLearnedRule ? (
                        <button
                          type="button"
                          className="statement-shortcut-card"
                          disabled={statementBusy}
                          onClick={() => {
                            void handleClarificationSubmit(primaryLearnedRule);
                          }}
                        >
                          <div className="statement-shortcut-top">
                            <span className="tag support">{text.learnedRules}</span>
                            <strong>{formatStatementRuleChoice(primaryLearnedRule, language, languageText)}</strong>
                          </div>
                          <p>{primaryLearnedRule.explanation}</p>
                        </button>
                      ) : null}
                      <textarea
                        className="statement-textarea compact"
                        value={clarificationReply}
                        onChange={(event) => setClarificationReply(event.target.value)}
                        placeholder={statementText.replyPlaceholder}
                      />
                      <div className="button-row">
                        <button
                          type="button"
                          className="primary-button"
                          disabled={statementBusy}
                          onClick={() => {
                            void handleClarificationSubmit();
                          }}
                        >
                          {statementText.sendReply}
                        </button>
                        <button type="button" className="ghost-button" onClick={openTelegramThread}>
                          {text.openBot}
                        </button>
                      </div>
                      <div className="section-divider">
                        <strong>{statementText.quickChoices}</strong>
                      </div>
                      <div className="quick-choice-grid">
                        {prioritizedQuickChoices.map((choice) => {
                          const learnedRule = findMatchingStatementRuleForChoice(currentStatementItem, choice);
                          const isLearned = Boolean(learnedRule);
                          const isSuggested =
                            !isLearned &&
                            currentStatementItem.suggested_account_type === choice.account_type &&
                            currentStatementItem.suggested_life_sector === choice.life_sector;
                          return (
                            <button
                              key={`${choice.account_type}:${choice.life_sector}`}
                              type="button"
                              className={
                                isLearned
                                  ? "ghost-button quick-choice-button learned"
                                  : isSuggested
                                    ? "ghost-button quick-choice-button suggested"
                                    : "ghost-button quick-choice-button"
                              }
                              disabled={statementBusy}
                              onClick={() => {
                                void handleClarificationSubmit(choice);
                              }}
                            >
                              <span className="quick-choice-content">
                                <span className="quick-choice-head">
                                  <span className="quick-choice-label">{choice.labels[language]}</span>
                                  {isLearned ? <span className="tag support">{text.learnedRules}</span> : null}
                                  {isSuggested ? <span className="tag watch">{statementText.suggestedBadge}</span> : null}
                                </span>
                                {learnedRule?.explanation ? <span className="quick-choice-detail">{learnedRule.explanation}</span> : null}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                      {currentStatementItem.matched_rules.length ? (
                        <>
                          <div className="section-divider">
                            <strong>{text.learnedRules}</strong>
                            <span>{text.replyHint}</span>
                          </div>
                          <div className="rules-list">
                            {currentStatementItem.matched_rules.map((rule) => (
                              <div
                                key={`${rule.match_key}:${rule.account_type}:${rule.life_sector}`}
                                className="rule-row statement-rule-row"
                              >
                                <div>
                                  <strong>{formatStatementRuleChoice(rule, language, languageText)}</strong>
                                  <span>{rule.match_key}</span>
                                </div>
                                <p>{rule.explanation}</p>
                              </div>
                            ))}
                          </div>
                        </>
                      ) : null}
                      <div className="helper-note">{statementText.textReplyHint}</div>
                    </article>
                  ) : (
                    <div className="empty-state">
                      <strong>{statementText.workbenchIdle}</strong>
                      <p>{statementText.workbenchIdleBody}</p>
                    </div>
                  )}
              <article className="quick-sheet-section">
                <div className="quick-sheet-section-head">
                  <div>
                    <span className="app-kicker">{text.learnedRules}</span>
                    <strong>{text.lastImport}</strong>
                  </div>
                </div>
                <div className="rules-list">
                  {micro.recent_rules.length ? (
                    micro.recent_rules.map((rule) => (
                      <div key={rule.match_key} className="rule-row">
                        <div>
                          <strong>{rule.match_key}</strong>
                          <span>{formatStatementRuleChoice(rule, language, languageText)}</span>
                        </div>
                        <p>{rule.explanation}</p>
                      </div>
                    ))
                  ) : (
                    <div className="empty-state">{text.noRules}</div>
                  )}
                </div>
                <div className="section-divider">
                  <strong>{statementText.historyTitle}</strong>
                  <span>{statementText.historyBody}</span>
                </div>
                {statementHistory.length ? (
                  <div className="statement-history-list">
                    {statementHistory.map((item) => {
                      const canResume =
                        item.remaining_clarifications > 0 && item.imported_statement_id === activeStatementImportId;
                      const isSelected = item.imported_statement_id === selectedStatementId;
                      return (
                        <article
                          key={item.imported_statement_id}
                          className={`statement-history-card${isSelected ? " selected" : ""}`}
                        >
                          <div className="clarification-top">
                            <strong>{item.source_name}</strong>
                            <span className={item.remaining_clarifications > 0 ? "tag urgent" : "tag planned"}>
                              {formatStatementParseStatus(item.parse_status, languageText)}
                            </span>
                          </div>
                          <div className="statement-history-grid">
                            <div>
                              <strong>{languageText.fileLabel}</strong>
                              <span>{item.original_filename ?? "telegram_text_statement"}</span>
                            </div>
                            <div>
                              <strong>{statementText.importedLabel}</strong>
                              <span>{formatDate(item.imported_at, locale)}</span>
                            </div>
                            <div>
                              <strong>{statementText.parsedLabel}</strong>
                              <span>{String(item.parsed_count ?? 0)}</span>
                            </div>
                            <div>
                              <strong>{statementText.autoLabel}</strong>
                              <span>{String(item.auto_count ?? 0)}</span>
                            </div>
                            <div>
                              <strong>{statementText.openLabel}</strong>
                              <span>{String(item.remaining_clarifications)}</span>
                            </div>
                          </div>
                          <div className="button-row statement-history-actions">
                            <button
                              type="button"
                              className={isSelected ? "primary-button" : "ghost-button"}
                              disabled={statementDetailBusy && isSelected}
                              onClick={() => {
                                setSelectedStatementId(item.imported_statement_id);
                              }}
                            >
                              {text.browserPreview}
                            </button>
                            <button
                              type="button"
                              className="ghost-button"
                              disabled={statementDownloadBusy}
                              onClick={() => {
                                void handleStatementSourceDownload(item);
                              }}
                            >
                              {statementDownloadTargetId === item.imported_statement_id
                                ? statementText.sourceDownloadBusy
                                : statementText.sourceDownloadAction}
                            </button>
                            {canResume ? (
                              <button
                                type="button"
                                className="primary-button"
                                disabled={statementBusy}
                                onClick={() => {
                                  void handleStatementHistoryResume();
                                }}
                              >
                                {statementText.historyResumeAction}
                              </button>
                            ) : null}
                            {canResume ? (
                              <button type="button" className="ghost-button" onClick={openTelegramThread}>
                                {text.openBot}
                              </button>
                            ) : null}
                          </div>
                          {canResume ? <p className="statement-history-note">{statementText.historyResumeHint}</p> : null}
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <div className="empty-state">{statementText.historyEmpty}</div>
                )}
                <div className="section-divider">
                  <strong>{text.browserPreview}</strong>
                  <span>{text.lastImport}</span>
                </div>
                {statementDetailError ? <div className="inline-status error">{statementDetailError}</div> : null}
                {statementDetailBusy && !selectedStatementDetail ? (
                  <div className="empty-state">{text.loading}</div>
                ) : selectedStatementDetail ? (
                  <article
                    className={`statement-detail-card${selectedStatementDetail.is_active ? " active" : ""}`}
                    ref={statementDetailCardRef}
                  >
                    <div className="clarification-top">
                      <div className="statement-detail-head">
                        <strong>{selectedStatementDetail.source_name}</strong>
                        <span>{formatStatementStorageSummary(selectedStatementDetail, language)}</span>
                      </div>
                      <div className="statement-detail-tags">
                        {selectedStatementDetail.is_active ? <span className="tag urgent">{text.pendingClarification}</span> : null}
                        <span
                          className={selectedStatementDetail.remaining_clarifications > 0 ? "tag urgent" : "tag planned"}
                        >
                          {formatStatementParseStatus(selectedStatementDetail.parse_status, languageText)}
                        </span>
                      </div>
                    </div>
                    <div className="statement-status-grid">
                      <div>
                        <strong>{languageText.fileLabel}</strong>
                        <span>{selectedStatementDetail.original_filename ?? "telegram_text_statement"}</span>
                      </div>
                      <div>
                        <strong>{statementText.importedLabel}</strong>
                        <span>{formatDate(selectedStatementDetail.imported_at, locale)}</span>
                      </div>
                      <div>
                        <strong>{statementText.parsedLabel}</strong>
                        <span>{String(selectedStatementDetail.parsed_count ?? 0)}</span>
                      </div>
                      <div>
                        <strong>{statementText.autoLabel}</strong>
                        <span>{String(selectedStatementDetail.auto_count ?? 0)}</span>
                      </div>
                      <div>
                        <strong>{statementText.openLabel}</strong>
                        <span>{String(selectedStatementDetail.remaining_clarifications)}</span>
                      </div>
                      <div>
                        <strong>{formatStatementRawLinesLabel(language)}</strong>
                        <span>{String(selectedStatementDetail.raw_line_count)}</span>
                      </div>
                    </div>
                    {selectedDetailItem ? (
                      <>
                        <div className="statement-progress-card">
                          <div className="statement-progress-top">
                            <strong>
                              {selectedDetailResolvedCount} / {selectedDetailTotalCount}
                            </strong>
                            <span>{selectedDetailProgressValue}%</span>
                          </div>
                          <div className="statement-progress-track" aria-hidden="true">
                            <span style={{ width: `${selectedDetailProgressValue}%` }} />
                          </div>
                          <div className="statement-progress-grid">
                            <div>
                              <strong>{statementText.parsedLabel}</strong>
                              <span>{String(selectedStatementDetail.parsed_count ?? 0)}</span>
                            </div>
                            <div>
                              <strong>{statementText.autoLabel}</strong>
                              <span>{String(selectedStatementDetail.auto_count ?? 0)}</span>
                            </div>
                            <div>
                              <strong>{text.status}</strong>
                              <span>{formatTransactionType(selectedDetailItem.transaction_type, language)}</span>
                            </div>
                            <div>
                              <strong>{statementText.openLabel}</strong>
                              <span>{String(selectedDetailRemainingCount)}</span>
                            </div>
                          </div>
                        </div>
                        <h3>
                          {formatMoney(selectedDetailItem.amount, locale)} · {selectedDetailItem.counterparty}
                        </h3>
                        <p>{selectedDetailItem.reason}</p>
                        <div className="statement-status-grid clarification-context-grid">
                          <div>
                            <strong>{statementText.importedLabel}</strong>
                            <span>{formatDate(selectedDetailItem.statement_date, locale)}</span>
                          </div>
                          <div>
                            <strong>{text.status}</strong>
                            <span>{formatTransactionType(selectedDetailItem.transaction_type, language)}</span>
                          </div>
                          <div>
                            <strong>{text.source}</strong>
                            <span>{selectedDetailItem.counterparty}</span>
                          </div>
                          <div>
                            <strong>{statementText.quickChoices}</strong>
                            <span>
                              {selectedDetailItem.suggested_account_type || selectedDetailItem.suggested_life_sector
                                ? resolveStatementSuggestionLabel(selectedDetailItem, language, languageText)
                                : statementText.livePrompt}
                            </span>
                          </div>
                        </div>
                        {selectedDetailQueuePreview.length ? (
                          <>
                            <div className="section-divider">
                              <strong>{statementText.openLabel}</strong>
                              <span>{selectedDetailQueuePreview.length} {languageText.flowItems}</span>
                            </div>
                            <div className="statement-queue-list">
                              {selectedDetailQueuePreview.map(({ item, active }) => {
                                const queueSuggestion = resolveStatementSuggestionLabel(item, language, languageText);
                                return (
                                  <article
                                    key={`${item.index}:${item.statement_date}:${item.counterparty}:${item.amount}`}
                                    className={active ? "statement-queue-card active" : "statement-queue-card"}
                                  >
                                    <div className="statement-queue-top">
                                      <span className={active ? "tag urgent" : "tag planned"}>
                                        {active ? statementText.livePrompt : formatDate(item.statement_date, locale)}
                                      </span>
                                      <strong>{formatMoney(item.amount, locale)}</strong>
                                    </div>
                                    <strong>{item.counterparty}</strong>
                                    <div className="statement-queue-meta">
                                      <span>{formatTransactionType(item.transaction_type, language)}</span>
                                      <span>{queueSuggestion ?? item.reason}</span>
                                    </div>
                                  </article>
                                );
                              })}
                            </div>
                          </>
                        ) : null}
                        <p className="clarification-meta">
                          {formatDate(selectedDetailItem.statement_date, locale)} · {selectedDetailItem.description}
                        </p>
                        <p className="clarification-hint">
                          {selectedDetailClarificationState?.promptMessage || statementText.livePrompt}
                        </p>
                        {selectedStatementDetail.is_active && selectedDetailRemainingCount > 0 ? (
                          <>
                            {selectedDetailPrimaryLearnedRule ? (
                              <button
                                type="button"
                                className="statement-shortcut-card"
                                disabled={statementBusy}
                                onClick={() => {
                                  void handleClarificationSubmit(selectedDetailPrimaryLearnedRule);
                                }}
                              >
                                <div className="statement-shortcut-top">
                                  <span className="tag support">{text.learnedRules}</span>
                                  <strong>{formatStatementRuleChoice(selectedDetailPrimaryLearnedRule, language, languageText)}</strong>
                                </div>
                                <p>{selectedDetailPrimaryLearnedRule.explanation}</p>
                              </button>
                            ) : null}
                            <textarea
                              className="statement-textarea compact"
                              value={clarificationReply}
                              onChange={(event) => setClarificationReply(event.target.value)}
                              placeholder={statementText.replyPlaceholder}
                            />
                            <div className="button-row">
                              <button
                                type="button"
                                className="primary-button"
                                disabled={statementBusy}
                                onClick={() => {
                                  void handleClarificationSubmit();
                                }}
                              >
                                {statementText.sendReply}
                              </button>
                              <button type="button" className="ghost-button" onClick={openTelegramThread}>
                                {text.openBot}
                              </button>
                            </div>
                            <div className="section-divider">
                              <strong>{statementText.quickChoices}</strong>
                              <span>{statementText.historyResumeHint}</span>
                            </div>
                            <div className="quick-choice-grid">
                              {selectedDetailPrioritizedQuickChoices.map((choice) => {
                                const learnedRule = findMatchingStatementRuleForChoice(selectedDetailItem, choice);
                                const isLearned = Boolean(learnedRule);
                                const isSuggested =
                                  !isLearned &&
                                  selectedDetailItem.suggested_account_type === choice.account_type &&
                                  selectedDetailItem.suggested_life_sector === choice.life_sector;
                                return (
                                  <button
                                    key={`detail:${choice.account_type}:${choice.life_sector}`}
                                    type="button"
                                    className={
                                      isLearned
                                        ? "ghost-button quick-choice-button learned"
                                        : isSuggested
                                          ? "ghost-button quick-choice-button suggested"
                                          : "ghost-button quick-choice-button"
                                    }
                                    disabled={statementBusy}
                                    onClick={() => {
                                      void handleClarificationSubmit(choice);
                                    }}
                                  >
                                    <span className="quick-choice-content">
                                      <span className="quick-choice-head">
                                        <span className="quick-choice-label">{choice.labels[language]}</span>
                                        {isLearned ? <span className="tag support">{text.learnedRules}</span> : null}
                                        {isSuggested ? <span className="tag watch">{statementText.suggestedBadge}</span> : null}
                                      </span>
                                      {learnedRule?.explanation ? (
                                        <span className="quick-choice-detail">{learnedRule.explanation}</span>
                                      ) : null}
                                    </span>
                                  </button>
                                );
                              })}
                            </div>
                            {selectedDetailItem.matched_rules.length ? (
                              <>
                                <div className="section-divider">
                                  <strong>{text.learnedRules}</strong>
                                  <span>{text.replyHint}</span>
                                </div>
                                <div className="rules-list">
                                  {selectedDetailItem.matched_rules.map((rule) => (
                                    <div
                                      key={`detail:${rule.match_key}:${rule.account_type}:${rule.life_sector}`}
                                      className="rule-row statement-rule-row"
                                    >
                                      <div>
                                        <strong>{formatStatementRuleChoice(rule, language, languageText)}</strong>
                                        <span>{rule.match_key}</span>
                                      </div>
                                      <p>{rule.explanation}</p>
                                    </div>
                                  ))}
                                </div>
                              </>
                            ) : null}
                          </>
                        ) : null}
                      </>
                    ) : null}
                    {selectedStatementDetail.note ? (
                      <p className="statement-history-note">{selectedStatementDetail.note}</p>
                    ) : null}
                    {selectedStatementDetail.raw_preview ? (
                      <pre className="statement-detail-preview">{selectedStatementDetail.raw_preview}</pre>
                    ) : (
                      <div className="empty-state">{formatStatementPreviewFallback(language)}</div>
                    )}
                    {selectedStatementDetail.raw_preview_truncated ? (
                      <p className="helper-note">{formatStatementPreviewTruncated(language)}</p>
                    ) : null}
                    {canDownloadSelectedStatementSource ||
                    (selectedStatementDetail.is_active && selectedStatementDetail.remaining_clarifications > 0) ? (
                      <div className="button-row statement-history-actions">
                        {canDownloadSelectedStatementSource ? (
                          <button
                            type="button"
                            className="ghost-button"
                            disabled={statementDownloadBusy}
                            onClick={() => {
                              void handleStatementSourceDownload(selectedStatementDetail);
                            }}
                          >
                            {statementDownloadTargetId === selectedStatementDetail.imported_statement_id
                              ? statementText.sourceDownloadBusy
                              : statementText.sourceDownloadAction}
                          </button>
                        ) : null}
                        {selectedStatementDetail.is_active && selectedStatementDetail.remaining_clarifications > 0 ? (
                          <>
                            <button
                              type="button"
                              className="primary-button"
                              disabled={statementBusy}
                              onClick={() => {
                                void handleStatementHistoryResume();
                              }}
                            >
                              {statementText.historyResumeAction}
                            </button>
                            <button type="button" className="ghost-button" onClick={openTelegramThread}>
                              {text.openBot}
                            </button>
                          </>
                        ) : null}
                      </div>
                    ) : null}
                  </article>
                ) : (
                  <div className="empty-state">{statementText.historyEmpty}</div>
                )}
              </article>
                      </div>
                    </Panel>
                  </motion.div>
                </motion.div>
              ) : null}
            </AnimatePresence>,
            document.body,
          )}

          {sceneTab === "sandbox" ? (
            <div className="page-grid" data-testid="scene-sandbox">
              <Panel title={text.sandboxTitle} subtitle={text.sandboxBody}>
                <SandboxGauge value={sandboxProbability} />
                <SandboxSlider
                  label={text.invest}
                  valueText={formatMoney(String(investment), locale)}
                  min={50000}
                  max={Math.max(600000, Math.round(safeAmount || 600000))}
                  step={5000}
                  value={investment}
                  minLabel={formatMoney("50000", locale)}
                  maxLabel={formatMoney(String(Math.max(600000, Math.round(safeAmount || 600000))), locale)}
                  testId="sandbox-investment-slider"
                  onChange={setInvestment}
                />
                <SandboxSlider
                  label={text.roi}
                  valueText={`${roi}%`}
                  min={5}
                  max={120}
                  step={1}
                  value={roi}
                  minLabel="5%"
                  maxLabel="120%"
                  testId="sandbox-roi-slider"
                  onChange={setRoi}
                />
                <SandboxSlider
                  label={sandboxText.lag}
                  valueText={`${lagDays}d`}
                  min={7}
                  max={60}
                  step={1}
                  value={lagDays}
                  minLabel="7d"
                  maxLabel="60d"
                  testId="sandbox-lag-slider"
                  onChange={setLagDays}
                />
                {sandboxError ? <div className="inline-status error">{sandboxError}</div> : null}
                {sandboxBusy ? <div className="inline-status">{sandboxText.modelingBusy}</div> : null}
                <div className="sandbox-grid">
                  <MetricCard
                    label={sandboxText.probability}
                    value={
                      sandboxResult
                        ? `${formatCount(sandboxResult.scorecard.probability_of_success, locale)}%`
                        : "..."
                    }
                    accent={
                      sandboxResult && asNumber(sandboxResult.scorecard.probability_of_success) >= 70 ? "mint" : "sky"
                    }
                  />
                  <MetricCard label={text.payback} value={formatMoney(projectedReturn, locale)} accent="mint" />
                  <MetricCard label={text.runway} value={`${formatCount(cashPressure, locale)}%`} accent={asNumber(cashPressure) > 55 ? "ember" : "sky"} />
                  <MetricCard label={languageText.paybackDays} value={`${paybackDays}d`} accent="ocean" />
                </div>
                {sandboxResult ? (
                  <div className="section-stack" data-testid="sandbox-verdict">
                    <div className="rationale-row">
                      <strong>{sandboxText.verdict}</strong>
                      <p>
                        {sandboxVerdictLabel} · {sandboxRunwayLabel}
                      </p>
                    </div>
                    <div className="rationale-row">
                      <strong>{sandboxText.pressureDelta}</strong>
                      <p>{formatMoney(sandboxResult.scorecard.max_delta_drawdown, locale)}</p>
                    </div>
                  </div>
                ) : null}
              </Panel>
              <Panel title={sandboxText.liveRationaleTitle} subtitle={sandboxText.liveRationaleBody}>
                {sandboxResult ? (
                  <div className="rationale-list">
                    {sandboxResult.agents.map((agent) => (
                      <div key={agent.agent} className="rationale-row">
                        <div className="rationale-top">
                          <strong>{agent.agent}</strong>
                          <span className={`tag ${agent.stance}`}>{formatAgentStance(agent.stance, languageText)}</span>
                        </div>
                        <p>{agent.summary}</p>
                        <div className="rationale-signals">
                          {agent.signals.map((signal) => (
                            <span key={signal}>{signal}</span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">{sandboxText.noPreview}</div>
                )}
              </Panel>
            </div>
          ) : null}

          {sceneTab === "settings" ? (
            <div className="page-grid" data-testid="scene-settings">
              <Panel title={text.settingsTitle} subtitle={text.settingsBody}>
                <div className="settings-list">
                  <SettingRow label={text.language} value={languageText.names[language]} />
                  <SettingRow
                    label={languageText.profileLanguage}
                    value={languageText.names[resolveLanguage(micro.preferred_language ?? language)]}
                  />
                  <SettingRow label={text.profile} value={micro.profile_name ?? text.noData} />
                  <SettingRow
                    label={text.onboarding}
                    value={micro.onboarding_completed ? text.complete : text.pending}
                  />
                  <SettingRow label={text.quickAdd} value={quickAddEndpointUrl} />
                  <SettingRow label={text.webApp} value={webAppUrl} />
                </div>
                <div className="section-divider">
                  <strong>{text.language}</strong>
                  <span>{languageText.settingsHint}</span>
                </div>
                <div className="language-row settings-language-grid" aria-label={text.language}>
                  {languageOptions.map((option) => (
                    <button
                      key={`settings-${option}`}
                      type="button"
                      className={option === language ? "language-pill active" : "language-pill"}
                      disabled={languageSaving}
                      onClick={() => {
                        void handleLanguageChange(option);
                      }}
                    >
                      {languageText.names[option]}
                    </button>
                  ))}
                </div>
                {languageSaving ? <div className="inline-status">{languageText.saving}</div> : null}
                {languageError ? <div className="inline-status error">{languageError}</div> : null}
                {languageNotice ? <div className="inline-status">{languageNotice}</div> : null}
              </Panel>
              <Panel title={text.settingsShortcutTitle} subtitle={text.settingsShortcutBody}>
                <div className="settings-list">
                  <SettingRow label={text.quickAdd} value={quickAddEndpointUrl} />
                  <SettingRow
                    label={text.settingsShortcutMode}
                    value={effectiveTelegramUserId ? text.settingsShortcutLinked : text.settingsShortcutPreview}
                  />
                  <SettingRow label={text.webApp} value={webAppUrl} />
                </div>
                <div className="inline-status">{text.settingsShortcutApiKey}</div>
                <div className="settings-code-grid">
                  <article className="settings-code-card">
                    <strong>{text.settingsShortcutHeaders}</strong>
                    <pre className="settings-code">{shortcutHeaderSample}</pre>
                  </article>
                  <article className="settings-code-card">
                    <strong>{text.settingsShortcutPayload}</strong>
                    <pre className="settings-code">{shortcutPayloadSample}</pre>
                  </article>
                </div>
                <article className="settings-code-card">
                  <strong>{text.settingsShortcutCurl}</strong>
                  <pre className="settings-code">{shortcutCurlSample}</pre>
                </article>
                <div className="button-row settings-actions">
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => {
                      openExternalLink(webAppUrl);
                    }}
                  >
                    {text.settingsShortcutOpen}
                  </button>
                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => {
                      openExternalLink("shortcuts://");
                    }}
                  >
                    Apple Siri Shortcuts
                  </button>
                </div>
              </Panel>
              <Panel title={text.settingsQalTitle} subtitle={text.settingsQalBody}>
                <div className="settings-topline">
                  <span className="tag support">{text.settingsQalBadge}</span>
                  <strong>{text.settingsQalStatus}: {qalStatusLabel}</strong>
                </div>
                <div className="sandbox-grid settings-metric-grid">
                  <MetricCard label={text.settingsQalScore} value={`${qalPreviewScore}`} accent="mint" />
                  <MetricCard label={text.settingsQalMint} value={`${qalMintWindow} QAL`} accent="sky" />
                  <MetricCard label={text.settingsQalSignals} value={`${qalActiveSignals}/${qalSignals.length}`} accent="ocean" />
                </div>
                <div className="settings-list">
                  {qalSignals.map((signal) => (
                    <SettingRow key={signal.label} label={signal.label} value={signal.value} />
                  ))}
                </div>
              </Panel>
              <Panel title={text.settingsMarketTitle} subtitle={text.settingsMarketBody}>
                {marketCards.length ? (
                  <div className="settings-card-grid">
                    {marketCards.map((card) => (
                      <article key={card.title} className="settings-card">
                        <div className="settings-card-top">
                          <strong>{card.title}</strong>
                          <span className={`tag ${card.tone}`}>{card.badge}</span>
                        </div>
                        <p>{card.body}</p>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">{text.settingsMarketEmpty}</div>
                )}
              </Panel>
              <Panel title={languageText.systemNotesTitle} subtitle={languageText.systemNotesBody}>
                <div className="settings-list">
                  <SettingRow label={languageText.apiLabel} value={apiBaseUrl} />
                  <SettingRow
                    label={languageText.userLabel}
                    value={effectiveTelegramUserId ? String(effectiveTelegramUserId) : statementText.previewHint}
                  />
                  <SettingRow label={languageText.asOfLabel} value={formatDate(micro.as_of, locale)} />
                </div>
              </Panel>
            </div>
          ) : null}
            </motion.section>
          </AnimatePresence>
        </section>

        {createPortal(
          <AnimatePresence>
            {summarySheetOpen ? (
              <motion.div
                className="summary-overlay"
                data-testid="summary-overlay"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
                onClick={closeSummarySheet}
              >
                <motion.div
                  className="summary-overlay-shell"
                  data-testid="summary-overlay-card"
                  initial={{ y: 18, opacity: 0.92, scale: 0.985 }}
                  animate={{ y: 0, opacity: 1, scale: 1 }}
                  exit={{ y: 22, opacity: 0.9, scale: 0.985 }}
                  transition={{ type: "spring", stiffness: 280, damping: 28, mass: 0.92 }}
                  onClick={(event) => {
                    event.stopPropagation();
                  }}
                >
                  <button
                    type="button"
                    className="ghost-button summary-overlay-close"
                    data-testid="summary-overlay-close"
                    onClick={closeSummarySheet}
                  >
                    {quickText.closeAction}
                  </button>
                  <Panel title={text.balance} subtitle={text.mapLead} className="summary-overlay-panel">
                    <div className="top-grid summary-grid">
                      <MetricCard label={text.business} value={formatMoney(macro.business_balance, locale)} accent="mint" />
                      <MetricCard label={text.personal} value={formatMoney(macro.personal_balance, locale)} accent="ocean" />
                      <MetricCard
                        label={text.safeToWithdraw}
                        value={formatMoney(medium.safe_to_withdraw.safe_amount, locale)}
                        accent="sunrise"
                      />
                      <MetricCard
                        label={text.clarifications}
                        value={String(activeIssuesCount)}
                        accent={activeIssuesCount > 0 ? "ember" : "sky"}
                      />
                    </div>
                  </Panel>
                </motion.div>
              </motion.div>
            ) : null}
          </AnimatePresence>,
          document.body,
        )}

        <nav className="tab-bar bottom-tabbar" aria-label="QALTAM tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              data-testid={`tab-${tab.id}`}
              aria-current={tab.id === activeTab ? "page" : undefined}
              className={
                tab.id === activeTab
                  ? `tab-button ${tab.id === "quick" ? "is-quick" : ""} active`
                  : `tab-button ${tab.id === "quick" ? "is-quick" : ""}`
              }
              onClick={() => handleTabPress(tab.id)}
            >
              <span className="tab-icon" aria-hidden="true">
                {tab.icon}
              </span>
              <span className="tab-label">{tab.label[language]}</span>
            </button>
          ))}
        </nav>
      </div>
    </main>
  );
}

function MetricCard({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <article className={`metric-card accent-${accent}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="info-pill">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Panel({
  title,
  subtitle,
  titleId,
  className,
  children,
}: React.PropsWithChildren<{ title: string; subtitle?: string; titleId?: string; className?: string }>) {
  return (
    <section className={className ? `panel ${className}` : "panel"}>
      <header className="panel-head">
        <div>
          <h2 id={titleId}>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
      </header>
      {children}
    </section>
  );
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="setting-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ProjectionChart({ points, locale }: { points: ProjectionPoint[]; locale: string }) {
  if (!points.length) {
    return <div className="empty-state">{miniAppLanguageCopy.en.projectionEmpty}</div>;
  }

  const values = points.map((point) => asNumber(point.closing_balance));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = Math.max(1, max - min);
  const path = values
    .map((value, index) => {
      const x = (index / Math.max(1, values.length - 1)) * 100;
      const y = 100 - ((value - min) / spread) * 100;
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");

  return (
    <div className="chart-shell">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="chart-svg" aria-label="Cashflow projection">
        <path d={path} className="chart-line" pathLength={1} />
      </svg>
      <div className="chart-meta">
        <span>{formatMoney(String(min), locale)}</span>
        <span>{formatMoney(String(max), locale)}</span>
      </div>
    </div>
  );
}

function BridgeOrbit({
  bridges,
  locale,
  flowLabel,
}: {
  bridges: DashboardMacro["bridge_totals"];
  locale: string;
  flowLabel: string;
}) {
  const topBridges = bridges.slice(0, 8);
  const [activeSlug, setActiveSlug] = useState<string>(topBridges[0]?.slug ?? "orbit");
  const activeBridge = topBridges.find((bridge) => bridge.slug === activeSlug) ?? topBridges[0];

  if (!activeBridge) {
    return <div className="empty-state">Bridge map is waiting for live data.</div>;
  }

  return (
    <div className="bridge-orbit">
      <div className="bridge-orbit-core">
        <span>11 bridges</span>
        <strong>{formatMoney(activeBridge.amount, locale)}</strong>
        <p>{activeBridge.label}</p>
      </div>
      {topBridges.map((bridge, index) => {
        const angle = (Math.PI * 2 * index) / Math.max(1, topBridges.length);
        const x = 50 + Math.cos(angle - Math.PI / 2) * 38;
        const y = 50 + Math.sin(angle - Math.PI / 2) * 38;
        const amount = asNumber(bridge.amount);
        const tone = amount >= 0 ? "positive" : amount <= -1 ? "negative" : "neutral";

        return (
          <motion.button
            key={bridge.slug}
            type="button"
            className={bridge.slug === activeBridge.slug ? `bridge-node ${tone} active` : `bridge-node ${tone}`}
            style={{ left: `${x}%`, top: `${y}%` }}
            whileTap={{ scale: 0.96 }}
            onClick={() => setActiveSlug(bridge.slug)}
          >
            <span>{bridge.label}</span>
            <strong>{formatCount(bridge.transaction_count, locale)}</strong>
          </motion.button>
        );
      })}
      <div className="bridge-orbit-footer">
        <strong>{activeBridge.label}</strong>
        <span>
          {formatCount(activeBridge.transaction_count, locale)} {flowLabel}
        </span>
      </div>
    </div>
  );
}

function BankCardRail({
  cards,
}: {
  cards: Array<{ id: string; title: string; subtitle: string; amount: string; tone: "sunrise" | "mint" | "ocean" }>;
}) {
  return (
    <div className="bank-card-rail" aria-label="Bank cards">
      {cards.map((card) => (
        <article key={card.id} className={`bank-card tone-${card.tone}`}>
          <div className="bank-card-top">
            <span>{card.title}</span>
            <span>•• {card.id.slice(0, 2).toUpperCase()}</span>
          </div>
          <strong>{card.amount}</strong>
          <p>{card.subtitle}</p>
        </article>
      ))}
    </div>
  );
}

function SandboxGauge({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  const rotation = -110 + clamped * 2.2;

  return (
    <div className="sandbox-gauge">
      <div className="sandbox-gauge-dial">
        <div className="sandbox-gauge-arc" />
        <motion.div
          className="sandbox-gauge-needle"
          animate={{ rotate: rotation }}
          transition={{ type: "spring", stiffness: 120, damping: 18 }}
        />
        <div className="sandbox-gauge-center">
          <span>PoS%</span>
          <strong>{Math.round(clamped)}</strong>
        </div>
      </div>
    </div>
  );
}

function SandboxSlider({
  label,
  valueText,
  min,
  max,
  step,
  value,
  minLabel,
  maxLabel,
  testId,
  onChange,
}: {
  label: string;
  valueText: string;
  min: number;
  max: number;
  step: number;
  value: number;
  minLabel: string;
  maxLabel: string;
  testId?: string;
  onChange: (nextValue: number) => void;
}) {
  const clamped = Math.max(min, Math.min(max, value));
  const percent = ((clamped - min) / Math.max(1, max - min)) * 100;

  return (
    <div className="slider-block">
      <div className="slider-head">
        <label className="slider-label">
          <span>{label}</span>
          <strong>{valueText}</strong>
        </label>
        <motion.span
          className="slider-badge"
          key={`${label}-${valueText}`}
          initial={{ scale: 0.9, opacity: 0.72 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 260, damping: 18 }}
        >
          {Math.round(percent)}%
        </motion.span>
      </div>
      <div className="slider-shell">
        <motion.span
          className="slider-fill"
          aria-hidden="true"
          animate={{ width: `${percent}%` }}
          transition={{ type: "spring", stiffness: 220, damping: 26 }}
        />
        <input
          data-testid={testId}
          className="sandbox-slider"
          type="range"
          min={String(min)}
          max={String(max)}
          step={String(step)}
          value={clamped}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      </div>
      <div className="slider-scale" aria-hidden="true">
        <span>{minLabel}</span>
        <span>{maxLabel}</span>
      </div>
    </div>
  );
}

function VoiceWave() {
  return (
    <div className="voice-wave" aria-hidden="true">
      {Array.from({ length: 14 }).map((_, index) => (
        <motion.span
          key={index}
          animate={{ scaleY: [0.5, 1, 0.35, 0.85] }}
          transition={{ duration: 1.15, repeat: Number.POSITIVE_INFINITY, delay: index * 0.06 }}
        />
      ))}
    </div>
  );
}

function resolveApiBaseUrl() {
  const query = new URLSearchParams(window.location.search);
  const fromQuery = query.get("api");
  if (fromQuery) {
    return fromQuery.replace(/\/$/, "");
  }
  const fromEnv = import.meta.env.VITE_API_BASE_URL;
  if (fromEnv) {
    return fromEnv.replace(/\/$/, "");
  }
  const hostname = window.location.hostname || "localhost";
  const port = window.location.port;
  const isLocalHost = hostname === "localhost" || hostname === "127.0.0.1";
  if (!isLocalHost && port !== "5173") {
    return window.location.origin.replace(/\/$/, "");
  }
  const protocol = window.location.protocol === "https:" ? "https:" : "http:";
  return `${protocol}//${hostname}:8000`;
}

function buildAbsoluteUrl(baseUrl: string, pathOrUrl: string | null | undefined) {
  if (!pathOrUrl) {
    return baseUrl;
  }
  if (/^https?:\/\//i.test(pathOrUrl)) {
    return pathOrUrl;
  }
  if (pathOrUrl.startsWith("/")) {
    return `${baseUrl.replace(/\/$/, "")}${pathOrUrl}`;
  }
  return `${baseUrl.replace(/\/$/, "")}/${pathOrUrl}`;
}

function buildApiUrl(
  baseUrl: string,
  path: string,
  query?: Record<string, string | number | null | undefined>,
) {
  const url = new URL(buildAbsoluteUrl(baseUrl, path));
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === null || value === undefined || value === "") {
      continue;
    }
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
      ...resolveActorHeaders(),
    },
  });
  if (!response.ok) {
    throw await createHttpError(response);
  }
  return (await response.json()) as T;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...resolveActorHeaders(),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await createHttpError(response);
  }
  return (await response.json()) as T;
}

async function patchJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "PATCH",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...resolveActorHeaders(),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await createHttpError(response);
  }
  return (await response.json()) as T;
}

async function postFormData<T>(url: string, body: FormData): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      ...resolveActorHeaders(),
    },
    body,
  });
  if (!response.ok) {
    throw await createHttpError(response);
  }
  return (await response.json()) as T;
}

async function fetchBlob(url: string): Promise<{ blob: Blob; filename: string | null }> {
  const response = await fetch(url, {
    headers: {
      ...resolveActorHeaders(),
    },
  });
  if (!response.ok) {
    throw await createHttpError(response);
  }
  return {
    blob: await response.blob(),
    filename: readAttachmentFilename(response.headers.get("Content-Disposition")),
  };
}

class HttpError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "HttpError";
    this.status = status;
  }
}

async function createHttpError(response: Response) {
  return new HttpError(await readErrorMessage(response), response.status);
}

async function readErrorMessage(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (payload.detail) {
      return payload.detail;
    }
  } catch {
    // Ignore JSON parsing and fall back to status text below.
  }
  return `Request failed with status ${response.status}`;
}

function resolveSandboxRiskLevel(roi: number, lagDays: number) {
  if (roi >= 70 || lagDays >= 35) {
    return "high";
  }
  if (roi >= 30 || lagDays >= 18) {
    return "medium";
  }
  return "low";
}

function isQuickAssistantPrompt(value: string) {
  const normalized = value.trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  if (/^\d/.test(normalized)) {
    return false;
  }
  if (/[?؟]$/.test(normalized)) {
    return true;
  }
  return ["сколько", "посчитай", "покажи", "итог", "summary", "how much", "calculate"].some((token) =>
    normalized.includes(token),
  );
}

function resolveActorContext(): ActorContext {
  const telegramUserId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id ?? null;
  const telegramChatId = telegramUserId;
  const workspaceRole = resolveWorkspaceRole(null);
  return {
    telegramUserId: telegramUserId ?? null,
    telegramChatId,
    workspaceRole,
  };
}

function resolveActorHeaders(): Record<string, string> {
  const actor = resolveActorContext();
  if (!actor.telegramUserId) {
    return {};
  }

  return {
    "X-Telegram-User-Id": String(actor.telegramUserId),
    "X-Telegram-Chat-Id": String(actor.telegramChatId ?? actor.telegramUserId),
    "X-Qaltam-Role": actor.workspaceRole,
  };
}

function formatRunwayLabel(value: string, text: SandboxCopy) {
  if (value === "inside_corridor") {
    return text.runwayInside;
  }
  if (value === "tight_corridor") {
    return text.runwayTight;
  }
  return text.runwayOutside;
}

function formatVerdict(value: string, text: SandboxCopy) {
  if (value === "approve") {
    return text.approve;
  }
  if (value === "stage") {
    return text.stage;
  }
  return text.hold;
}

function formatAgentStance(value: string, text: MiniAppLanguageCopy) {
  return text.agentStance[value] ?? value;
}

function formatStatementParseStatus(value: string, text: MiniAppLanguageCopy) {
  return text.parseStatus[value] ?? value;
}

function formatAccountType(value: string, text: MiniAppLanguageCopy) {
  return text.accountType[value] ?? value;
}

function formatTransactionType(value: string, language: Language) {
  if (language === "kk") {
    return { income: "Кіріс", expense: "Шығыс", transfer: "Аударым" }[value] ?? value;
  }
  if (language === "uk") {
    return { income: "Дохід", expense: "Витрата", transfer: "Переказ" }[value] ?? value;
  }
  if (language === "en") {
    return { income: "Income", expense: "Expense", transfer: "Transfer" }[value] ?? value;
  }
  return { income: "Доход", expense: "Расход", transfer: "Перевод" }[value] ?? value;
}

function formatStatementStorageSummary(detail: StatementDetail, language: Language) {
  if (language === "kk") {
    if (detail.storage_kind === "local_file") {
      return detail.file_available ? "Жергілікті файл сақталған" : "Сақталған файл табылмады";
    }
    return "Мәтіндік импорттың көшірмесі";
  }
  if (language === "uk") {
    if (detail.storage_kind === "local_file") {
      return detail.file_available ? "Локальний файл збережено" : "Збережений файл відсутній";
    }
    return "Знімок текстового імпорту";
  }
  if (language === "en") {
    if (detail.storage_kind === "local_file") {
      return detail.file_available ? "Local file retained" : "Stored file missing";
    }
    return "Text import snapshot";
  }
  if (detail.storage_kind === "local_file") {
    return detail.file_available ? "Локальный файл сохранен" : "Сохраненный файл не найден";
  }
  return "Снимок текстового импорта";
}

function canDownloadStatementSource(detail: StatementDetail) {
  return detail.file_available || detail.raw_line_count > 0;
}

function resolveStatementSourceFilename(target: StatementSourceTarget) {
  const sourceName = target.original_filename?.trim() || target.source_name?.trim() || `statement-${target.imported_statement_id}`;
  const normalized = sourceName.split(/[\\/]/).pop()?.trim() || `statement-${target.imported_statement_id}`;
  if (target.storage_kind === "virtual_text" && !/\.[a-z0-9]+$/i.test(normalized)) {
    return `${normalized}.txt`;
  }
  return normalized;
}

function readAttachmentFilename(contentDisposition: string | null) {
  if (!contentDisposition) {
    return null;
  }
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }
  const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1] ?? null;
}

function triggerBrowserDownload(blob: Blob, filename: string) {
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => {
    URL.revokeObjectURL(objectUrl);
  }, 0);
}

function formatStatementPreviewFallback(language: Language) {
  if (language === "kk") {
    return "Бұл импорт үшін бастапқы жолдар сақталмаған.";
  }
  if (language === "uk") {
    return "Для цього імпорту не збережено вихідних рядків.";
  }
  if (language === "en") {
    return "No raw source lines were retained for this import.";
  }
  return "Для этого импорта не сохранены исходные строки.";
}

function formatStatementPreviewTruncated(language: Language) {
  if (language === "kk") {
    return "Бастапқы жолдар жылдам тексеру үшін қысқартылды.";
  }
  if (language === "uk") {
    return "Вихідні рядки скорочено для швидкої перевірки.";
  }
  if (language === "en") {
    return "Raw lines trimmed for a quick review.";
  }
  return "Сырые строки сокращены для быстрой проверки.";
}

function formatStatementRawLinesLabel(language: Language) {
  if (language === "kk") {
    return "Шикі жолдар";
  }
  if (language === "uk") {
    return "Сирі рядки";
  }
  if (language === "en") {
    return "Raw lines";
  }
  return "Сырые строки";
}

function localeByLanguage(language: Language) {
  if (language === "kk") {
    return "kk-KZ";
  }
  if (language === "uk") {
    return "uk-UA";
  }
  if (language === "en") {
    return "en-US";
  }
  return "ru-RU";
}

function formatMoney(value: string | number | null | undefined, locale: string) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KZT",
    maximumFractionDigits: 0,
  }).format(asNumber(value));
}

function formatCount(value: string | number | null | undefined, locale: string) {
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: 2,
  }).format(asNumber(value));
}

function formatSignedPercent(value: string | number | null | undefined, locale: string) {
  const amount = asNumber(value);
  const prefix = amount > 0 ? "+" : "";
  return `${prefix}${new Intl.NumberFormat(locale, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amount)}%`;
}

function formatDate(value: string, locale: string) {
  return new Intl.DateTimeFormat(locale, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

function asNumber(value: string | number | null | undefined) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function resolveStringQueryParam(key: string): string | null {
  const query = new URLSearchParams(window.location.search);
  return query.get(key);
}

function resolveInitialLanguage(): Language {
  const storedLanguage = readStoredLanguagePreference();
  if (storedLanguage) {
    return storedLanguage;
  }
  return resolveLanguage(window.Telegram?.WebApp?.initDataUnsafe?.user?.language_code);
}

function resolveInitialTab(): TabId {
  return resolveTabQueryParam(resolveStringQueryParam("tab"));
}

function resolveInitialFocus(): DeepLinkFocus | null {
  return resolveFocusQueryParam(resolveStringQueryParam("focus"));
}

function resolveInitialStatementId(): number | null {
  return resolveStatementIdQueryParam(resolveStringQueryParam("statement_id"));
}

function resolveTabQueryParam(value: string | null): TabId {
  switch (value) {
    case "cashier":
    case "quick":
    case "sandbox":
    case "settings":
      return value;
    default:
      return "map";
  }
}

function resolveFocusQueryParam(value: string | null): DeepLinkFocus | null {
  if (value === "clarify" || value === "statement") {
    return value;
  }
  return null;
}

function resolveStatementIdQueryParam(value: string | null): number | null {
  if (!value) {
    return null;
  }

  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function syncActiveTabQuery(tab: TabId) {
  const url = new URL(window.location.href);
  const currentTab = resolveTabQueryParam(url.searchParams.get("tab"));
  if (currentTab === tab && (tab !== "map" || !url.searchParams.has("tab"))) {
    return;
  }

  if (tab === "map") {
    url.searchParams.delete("tab");
  } else {
    url.searchParams.set("tab", tab);
  }

  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function syncStatementSelectionQuery(tab: TabId, statementId: number | null) {
  const url = new URL(window.location.href);
  const currentStatementId = resolveStatementIdQueryParam(url.searchParams.get("statement_id"));

  if (tab !== "quick" || statementId === null) {
    if (!url.searchParams.has("statement_id")) {
      return;
    }
    url.searchParams.delete("statement_id");
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    return;
  }

  if (currentStatementId === statementId) {
    return;
  }

  url.searchParams.set("statement_id", String(statementId));
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function consumeInitialFocus() {
  const url = new URL(window.location.href);
  if (!url.searchParams.has("focus")) {
    return;
  }
  url.searchParams.delete("focus");
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function persistLanguagePreference(language: Language) {
  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Ignore storage failures and keep the in-memory preference.
  }
}

function readStoredLanguagePreference(): Language | null {
  try {
    const value = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return isLanguage(value) ? value : null;
  } catch {
    return null;
  }
}

function isLanguage(value: string | null): value is Language {
  return value === "ru" || value === "kk" || value === "en" || value === "uk";
}

function resolveWorkspaceRole(value: string | null): WorkspaceRole {
  if (!value) {
    return "owner";
  }

  const normalized = value.trim().toLowerCase().replace(/-/g, "_").replace(/\s+/g, "_");
  if (normalized === "cfo" || normalized === "coo" || normalized === "cashier" || normalized === "owner") {
    return normalized;
  }
  if (normalized === "family" || normalized === "family_member" || normalized === "familymember") {
    return "family_member";
  }
  return "owner";
}

function getCurrentStatementItem(pending: StatementPending | null) {
  if (pending?.current_item) {
    return pending.current_item;
  }
  if (!pending?.items.length) {
    return null;
  }
  return pending.items[pending.current_index] ?? pending.items[0] ?? null;
}

function getRemainingClarifications(pending: StatementPending | null) {
  if (!pending) {
    return 0;
  }
  if (typeof pending.remaining_count === "number") {
    return Math.max(0, pending.remaining_count);
  }
  return Math.max(0, pending.items.length - pending.current_index);
}

function getTotalClarifications(pending: StatementPending | null) {
  if (!pending) {
    return 0;
  }
  if (typeof pending.total_count === "number") {
    return Math.max(0, pending.total_count);
  }
  return pending.items.length;
}

function getResolvedClarifications(pending: StatementPending | null) {
  if (!pending) {
    return 0;
  }
  if (typeof pending.resolved_count === "number") {
    return Math.max(0, pending.resolved_count);
  }
  return Math.min(Math.max(0, pending.current_index), getTotalClarifications(pending));
}

function getClarificationCardState(
  pending: StatementPending | null,
  fallback: PendingClarification | null,
): {
  statementId: number | null;
  item: StatementPendingItem;
  totalCount: number;
  resolvedCount: number;
  remainingCount: number;
  promptMessage: string | null;
} | null {
  const currentItem = getCurrentStatementItem(pending);
  if (currentItem) {
    return {
      statementId: pending?.statement_id ?? null,
      item: currentItem,
      totalCount: getTotalClarifications(pending),
      resolvedCount: getResolvedClarifications(pending),
      remainingCount: getRemainingClarifications(pending),
      promptMessage: pending?.prompt_message ?? null,
    };
  }
  if (!fallback) {
    return null;
  }
  return {
    statementId: fallback.statement_id,
    item: buildStatementPendingItemFromFallback(fallback.current_item),
    totalCount: Math.max(fallback.parsed_count - fallback.auto_count, fallback.remaining_count),
    resolvedCount: Math.max(
      0,
      Math.max(fallback.parsed_count - fallback.auto_count, fallback.remaining_count) - fallback.remaining_count,
    ),
    remainingCount: fallback.remaining_count,
    promptMessage: null,
  };
}

function buildStatementPendingItemFromFallback(item: PendingClarification["current_item"]): StatementPendingItem {
  return {
    index: item.index,
    statement_date: item.statement_date,
    amount: item.amount,
    transaction_type: item.transaction_type,
    counterparty: item.counterparty,
    description: item.description,
    reason: item.reason,
    suggested_account_type: item.suggested_account_type,
    suggested_life_sector: item.suggested_life_sector,
    matched_rules: item.matched_rules,
  };
}

function formatStatementLifeSector(value: string | null, language: Language) {
  if (!value) {
    return "";
  }

  const matchedChoice = statementQuickChoices.find((choice) => choice.life_sector === value);
  if (matchedChoice) {
    return matchedChoice.labels[language];
  }

  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatStatementRuleChoice(
  item: Pick<ClarificationRulePreview, "account_type" | "life_sector">,
  language: Language,
  languageText: MiniAppLanguageCopy,
) {
  const matchedChoice = statementQuickChoices.find(
    (choice) => choice.account_type === item.account_type && choice.life_sector === item.life_sector,
  );
  if (matchedChoice) {
    return matchedChoice.labels[language];
  }

  const accountLabel =
    languageText.accountType[item.account_type] ??
    item.account_type.charAt(0).toUpperCase() + item.account_type.slice(1);
  const sectorLabel = formatStatementLifeSector(item.life_sector, language);
  return sectorLabel ? `${accountLabel} / ${sectorLabel}` : accountLabel;
}

function resolveStatementSuggestionLabel(
  item: Pick<StatementPendingItem, "suggested_account_type" | "suggested_life_sector"> | null,
  language: Language,
  languageText: MiniAppLanguageCopy,
) {
  if (!item) {
    return null;
  }

  const matchedChoice = statementQuickChoices.find(
    (choice) =>
      choice.account_type === item.suggested_account_type && choice.life_sector === item.suggested_life_sector,
  );
  if (matchedChoice) {
    return matchedChoice.labels[language];
  }

  if (!item.suggested_account_type && !item.suggested_life_sector) {
    return null;
  }

  return formatStatementRuleChoice(
    {
      account_type: item.suggested_account_type ?? "personal",
      life_sector: item.suggested_life_sector ?? "",
    },
    language,
    languageText,
  );
}

function buildClarificationQueuePreview(
  pending: StatementPending | null,
  fallback: PendingClarification | null,
): Array<{ item: StatementPendingItem; active: boolean }> {
  if (pending?.items.length) {
    const currentItem = getCurrentStatementItem(pending);
    const fallbackIndex = Math.max(0, Math.min(pending.current_index, pending.items.length - 1));
    const currentIndex =
      currentItem ? pending.items.findIndex((candidate) => candidate.index === currentItem.index) : fallbackIndex;
    const queueStartIndex = currentIndex >= 0 ? currentIndex : fallbackIndex;
    return pending.items.slice(queueStartIndex, queueStartIndex + 4).map((item, offset) => ({
      item,
      active: currentItem ? item.index === currentItem.index : offset === 0,
    }));
  }

  if (!fallback) {
    return [];
  }

  return [{ item: buildStatementPendingItemFromFallback(fallback.current_item), active: true }];
}

function buildSampleStatementText() {
  return [
    "2026-08-10 Client LLP +150000 advance payment",
    "2026-08-11 Arman Transfer -45000 personal transfer",
    "2026-08-12 Magnum Grocery -18250 family food",
  ].join("\n");
}

function resolveLanguage(languageCode?: string): Language {
  if (!languageCode) {
    return "ru";
  }
  if (languageCode.startsWith("kk")) {
    return "kk";
  }
  if (languageCode.startsWith("uk")) {
    return "uk";
  }
  if (languageCode.startsWith("en")) {
    return "en";
  }
  return "ru";
}

function applyTelegramTheme(theme?: TelegramTheme) {
  if (!theme) {
    return;
  }
  const root = document.documentElement;
  if (theme.bg_color) {
    root.style.setProperty("--telegram-bg", theme.bg_color);
  }
  if (theme.secondary_bg_color) {
    root.style.setProperty("--telegram-surface", theme.secondary_bg_color);
  }
  if (theme.text_color) {
    root.style.setProperty("--telegram-text", theme.text_color);
  }
  if (theme.hint_color) {
    root.style.setProperty("--telegram-muted", theme.hint_color);
  }
  if (theme.button_color) {
    root.style.setProperty("--telegram-accent", theme.button_color);
  }
}

function applyTelegramViewportInsets(inset?: TelegramSafeAreaInset) {
  if (!inset) {
    return;
  }
  const root = document.documentElement;
  const edges: Array<keyof TelegramSafeAreaInset> = ["top", "right", "bottom", "left"];
  edges.forEach((edge) => {
    const value = inset[edge];
    if (typeof value === "number" && Number.isFinite(value)) {
      root.style.setProperty(`--safe-${edge}`, `${value}px`);
    }
  });
}

function buildEmptyDashboard(telegramUserId?: number): DashboardBundle {
  const now = new Date().toISOString();
  return {
    macro: {
      as_of: now,
      total_balance: "0",
      business_balance: "0",
      personal_balance: "0",
      monthly_income: "0",
      monthly_expense: "0",
      account_balances: [],
      bridge_totals: [
        { slug: "sales_income", label: "Sales / Income", amount: "0", transaction_count: 0 },
        { slug: "inventory_parts", label: "Inventory / Parts", amount: "0", transaction_count: 0 },
        { slug: "payroll_team", label: "Payroll / Team", amount: "0", transaction_count: 0 },
        { slug: "rent_utilities", label: "Rent / Utilities", amount: "0", transaction_count: 0 },
        { slug: "logistics_transport", label: "Logistics / Transport", amount: "0", transaction_count: 0 },
        { slug: "marketing_growth", label: "Marketing / Growth", amount: "0", transaction_count: 0 },
        { slug: "taxes_fees", label: "Taxes / Fees", amount: "0", transaction_count: 0 },
        { slug: "tools_software", label: "Tools / Software", amount: "0", transaction_count: 0 },
        { slug: "owner_draw", label: "Owner Draw", amount: "0", transaction_count: 0 },
        { slug: "family_living", label: "Family / Living", amount: "0", transaction_count: 0 },
        { slug: "savings_debt", label: "Savings / Debt", amount: "0", transaction_count: 0 },
      ],
      imported_statements_total: 0,
      clarification_open_total: 0,
    },
    medium: {
      as_of: now,
      safe_to_withdraw: {
        safe_amount: "0",
        reserve_buffer: "0",
        projected_gap_date: null,
        available_business_balance: "0",
        upcoming_obligations_total: "0",
      },
      projection: [],
      gap_scenarios: [],
      obligations_total: "0",
      recent_receipts_total: 0,
      recent_receipts_amount: "0",
      tracked_skus_total: 0,
      inflation_leaders: [],
      last_receipt: null,
      recent_transactions: [],
    },
    micro: {
      as_of: now,
      profile_name: telegramUserId ? `Telegram user ${telegramUserId}` : null,
      preferred_language: null,
      onboarding_completed: null,
      pending_clarification: null,
      recent_rules: [],
      last_import: null,
      webapp_url: window.location.href,
      quick_add_path: "/api/v1/transactions",
    },
  };
}

function openTelegramThread() {
  const webApp = window.Telegram?.WebApp;
  const query = new URLSearchParams(window.location.search);
  const link = query.get("telegram_link") || import.meta.env.VITE_TELEGRAM_THREAD_URL || "https://t.me/";
  if (webApp?.openTelegramLink) {
    webApp.openTelegramLink(link);
    return;
  }
  if (webApp?.openLink) {
    webApp.openLink(link);
    return;
  }
  window.open(link, "_blank", "noopener,noreferrer");
}

function openExternalLink(link: string) {
  const webApp = window.Telegram?.WebApp;
  if (webApp?.openLink) {
    webApp.openLink(link);
    return;
  }
  window.open(link, "_blank", "noopener,noreferrer");
}

function triggerTelegramSelectionHaptic() {
  window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.();
}

function triggerTelegramImpact(style: TelegramHapticImpactStyle = "light") {
  window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.(style);
}

function triggerTelegramNotification(type: TelegramHapticNotificationType) {
  window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.(type);
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
