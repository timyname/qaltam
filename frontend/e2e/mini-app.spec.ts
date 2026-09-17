import { expect, test, type Browser, type BrowserContext, type Locator, type Page } from "@playwright/test";

type TelegramUser = {
  id: number;
  firstName: string;
  username: string;
};

async function createTelegramSession(browser: Browser, user: TelegramUser) {
  const context = await browser.newContext({ locale: "ru-RU" });
  await context.addInitScript(({ telegramUser }) => {
    const noop = () => undefined;
    const eventMap = new Map<string, Set<() => void>>();
    let backHandler: (() => void) | null = null;

    const webApp = {
      initDataUnsafe: {
        user: {
          id: telegramUser.id,
          first_name: telegramUser.firstName,
          username: telegramUser.username,
          language_code: "ru",
        },
      },
      themeParams: {
        bg_color: "#0b0d12",
        secondary_bg_color: "#101521",
        text_color: "#f8fafc",
        hint_color: "#94a3b8",
        button_color: "#f97316",
      },
      safeAreaInset: { top: 0, right: 0, bottom: 0, left: 0 },
      contentSafeAreaInset: { top: 0, right: 0, bottom: 0, left: 0 },
      ready: noop,
      expand: noop,
      requestFullscreen: noop,
      setBackgroundColor: noop,
      setHeaderColor: noop,
      setBottomBarColor: noop,
      enableVerticalSwipes: noop,
      disableVerticalSwipes: noop,
      enableClosingConfirmation: noop,
      disableClosingConfirmation: noop,
      openTelegramLink: noop,
      openLink: noop,
      onEvent: (event: string, callback: () => void) => {
        const listeners = eventMap.get(event) ?? new Set<() => void>();
        listeners.add(callback);
        eventMap.set(event, listeners);
      },
      offEvent: (event: string, callback: () => void) => {
        eventMap.get(event)?.delete(callback);
      },
      BackButton: {
        show: noop,
        hide: noop,
        onClick: (callback: () => void) => {
          backHandler = callback;
        },
        offClick: (callback: () => void) => {
          if (backHandler === callback) {
            backHandler = null;
          }
        },
      },
      HapticFeedback: {
        selectionChanged: noop,
        impactOccurred: noop,
        notificationOccurred: noop,
      },
    };

    Object.defineProperty(window, "Telegram", {
      configurable: true,
      value: {
        WebApp: webApp,
      },
    });
  }, { telegramUser: user });

  const page = await context.newPage();
  await page.goto("/");
  await expect(page.getByTestId("home-summary-card")).toBeVisible();
  await expect.poll(() => readMoney(page.getByTestId("balance-total"))).toBe(0);
  return { context, page };
}

async function readMoney(locator: Locator) {
  const text = await locator.innerText();
  const normalized = text.replace(/[−-]/g, "-").replace(/[^\d-]/g, "");
  return Number(normalized || "0");
}

async function openQuick(page: Page) {
  if (!(await page.getByTestId("scene-quick").isVisible())) {
    await page.getByTestId("tab-quick").click();
  }
  await expect(page.getByTestId("scene-quick")).toBeVisible();
  await expect(page.getByTestId("quick-draft-input")).toBeVisible();
}

async function submitQuick(page: Page, draft: string, account: "business" | "personal") {
  await openQuick(page);
  await page.getByTestId(account === "business" ? "quick-account-business" : "quick-account-personal").click();
  await page.getByTestId("quick-draft-input").fill(draft);
  await page.getByTestId("quick-submit").click();
}

async function closeQuick(page: Page) {
  if (await page.getByTestId("scene-quick").isVisible()) {
    await page.getByTestId("quick-close").click();
    await expect(page.getByTestId("scene-quick")).toBeHidden();
  }
}

async function assertAllTabs(page: Page) {
  await closeQuick(page);
  await page.getByTestId("tab-map").click();
  await expect(page.getByTestId("scene-map")).toBeVisible();

  await page.getByTestId("tab-cashier").click();
  await expect(page.getByTestId("scene-cashier")).toBeVisible();

  await page.getByTestId("tab-quick").click();
  await expect(page.getByTestId("scene-quick")).toBeVisible();
  await closeQuick(page);

  await page.getByTestId("tab-sandbox").click();
  await expect(page.getByTestId("scene-sandbox")).toBeVisible();
  await expect(page.getByTestId("sandbox-verdict")).toBeVisible();

  await page.getByTestId("tab-settings").click();
  await expect(page.getByTestId("scene-settings")).toBeVisible();
}

async function assertHeaderStatsOverlay(page: Page) {
  await page.getByTestId("tab-settings").click();
  await expect(page.getByTestId("home-summary-card")).toBeHidden();
  await expect(page.getByTestId("header-summary-toggle")).toBeVisible();

  await page.getByTestId("header-summary-toggle").click();
  await expect(page.getByTestId("summary-overlay")).toBeVisible();
  await expect(page.getByTestId("summary-overlay-card")).toBeVisible();

  await page.getByTestId("summary-overlay-close").click();
  await expect(page.getByTestId("summary-overlay")).toBeHidden();
}

async function assertBalanceOnMap(page: Page, expected: number) {
  await closeQuick(page);
  await page.getByTestId("tab-map").click();
  await expect(page.getByTestId("home-summary-card")).toBeVisible();
  await expect.poll(() => readMoney(page.getByTestId("balance-total"))).toBe(expected);
}

test("Mini App изолирует пользователей, переключает 5 вкладок и сохраняет ввод в живые данные", async ({ browser }) => {
  test.setTimeout(180_000);
  const userA = await createTelegramSession(browser, {
    id: 710001,
    firstName: "User",
    username: "user_a",
  });
  let userB: { context: BrowserContext; page: Page } | null = null;

  try {
    await submitQuick(userA.page, "+50000 выручка", "business");
    await expect(userA.page.getByTestId("quick-transaction-result")).toContainText("выручка");
    await assertBalanceOnMap(userA.page, 50_000);

    await submitQuick(userA.page, "такси 1200", "personal");
    await expect(userA.page.getByTestId("quick-transaction-result")).toContainText("такси");
    await assertBalanceOnMap(userA.page, 48_800);

    await submitQuick(userA.page, "Сколько ушло на такси?", "personal");
    const assistantResult = userA.page.getByTestId("quick-assistant-result");
    await expect(assistantResult).toBeVisible();
    await expect(assistantResult).toContainText("1200");

    await assertAllTabs(userA.page);
    await assertHeaderStatsOverlay(userA.page);

    userB = await createTelegramSession(browser, {
      id: 710002,
      firstName: "User",
      username: "user_b",
    });
    await expect.poll(() => readMoney(userB.page.getByTestId("balance-total"))).toBe(0);
    await assertAllTabs(userB.page);

    await submitQuick(userB.page, "бар 700", "personal");
    await expect(userB.page.getByTestId("quick-transaction-result")).toContainText("бар");
    await assertBalanceOnMap(userB.page, -700);

    await userA.page.getByTestId("tab-map").click();
    await expect(userA.page.getByTestId("home-summary-card")).toBeVisible();
    await userA.page.reload();
    await expect(userA.page.getByTestId("home-summary-card")).toBeVisible();
    await expect.poll(() => readMoney(userA.page.getByTestId("balance-total"))).toBe(48_800);
  } finally {
    await userA.context.close().catch(() => undefined);
    if (userB) {
      await userB.context.close().catch(() => undefined);
    }
  }
});
