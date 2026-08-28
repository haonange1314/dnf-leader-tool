import { expect, type Page, test } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "团长工作台" })).toBeVisible();
  await page.getByRole("button", { name: "进入工作台" }).click();
  await expect(page.getByText("12 人团本 · 智能排表工作台")).toBeVisible();
}

test("Owner can create a player and character through the browser", async ({ page }) => {
  await login(page);
  const suffix = Date.now().toString(36);
  const playerName = `E2E 玩家 ${suffix}`;
  const characterName = `E2E 角色 ${suffix}`;

  await page.getByRole("menuitem", { name: "人员管理" }).click();
  await page.getByRole("button", { name: "新增玩家" }).click();
  const playerModal = page.locator(".ant-modal").filter({ hasText: "新增玩家" });
  await playerModal.getByLabel("玩家称呼").fill(playerName);
  await playerModal.locator(".ant-btn-primary").click();
  await expect(page.getByText(playerName)).toBeVisible();

  await page.getByRole("button", { name: "添加角色", exact: true }).click();
  const characterModal = page
    .locator(".ant-modal")
    .filter({ hasText: `为 ${playerName} 添加角色` });
  await characterModal.getByLabel("角色名").fill(characterName);
  await characterModal.getByLabel("职业").fill("测试职业");
  await characterModal.getByLabel("伤害 / 增益评分").fill("500");
  await characterModal.locator(".ant-btn-primary").click();
  await page.locator(".ant-collapse-header").filter({ hasText: playerName }).click();
  await expect(page.getByText(characterName)).toBeVisible();
});

test("a second browser session is downgraded while the first holds the edit lease", async ({
  browser,
  page,
}) => {
  await login(page);
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "dnf_csrf");
  expect(csrf?.value).toBeTruthy();
  const dungeonsResponse = await page.request.get("/api/v1/dungeons");
  expect(dungeonsResponse.ok()).toBeTruthy();
  const dungeons = (await dungeonsResponse.json()) as {
    items: Array<{ versions: Array<{ id: string; status: string }> }>;
  };
  const version = dungeons.items[0].versions.find((item) => item.status === "PUBLISHED");
  expect(version).toBeTruthy();
  const scheduleName = `E2E 单编辑 ${Date.now().toString(36)}`;
  const createResponse = await page.request.post("/api/v1/schedules", {
    headers: { "X-CSRF-Token": csrf?.value ?? "" },
    data: { name: scheduleName, dungeonVersionId: version?.id },
  });
  expect(createResponse.status()).toBe(201);

  await page.getByRole("menuitem", { name: "排表管理" }).click();
  await page.getByText(scheduleName).click();
  await expect(page.getByText("已获得此排表的单编辑会话锁")).toBeVisible();
  await expect(page.getByText(/12 波 · revision 1/)).toBeVisible();

  const secondContext = await browser.newContext();
  const secondPage = await secondContext.newPage();
  try {
    await login(secondPage);
    await secondPage.getByRole("menuitem", { name: "排表管理" }).click();
    await secondPage.getByText(scheduleName).click();
    await expect(secondPage.getByText("当前由 admin 编辑")).toBeVisible();
    await expect(secondPage.getByRole("button", { name: /自动排表/ })).toBeDisabled();
  } finally {
    await secondContext.close();
  }
});
