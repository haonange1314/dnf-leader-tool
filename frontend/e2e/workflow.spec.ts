import { expect, type Locator, type Page, test } from "@playwright/test";

async function reorderByKeyboard(
  page: Page,
  handle: Locator,
  direction: "ArrowLeft" | "ArrowUp",
) {
  await handle.focus();
  await page.keyboard.press("Space");
  await page.waitForTimeout(100);
  await page.keyboard.press(direction);
  await page.waitForTimeout(100);
  await page.keyboard.press("Space");
}

async function login(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "团长工作台" })).toBeVisible();
  await page.getByRole("button", { name: "进入工作台" }).click();
  await expect(page.getByText("12 人团本 · 智能排表工作台")).toBeVisible();
}

test("Owner can create, edit, and deactivate personnel through the browser", async ({
  page,
}) => {
  await login(page);
  const suffix = Date.now().toString(36);
  const playerName = `E2E 玩家 ${suffix}`;
  const secondPlayerName = `E2E 排序玩家 ${suffix}`;
  const updatedPlayerName = `${playerName} 改`;

  await page.getByRole("menuitem", { name: "人员管理" }).click();
  await page.getByRole("button", { name: "新增玩家" }).click();
  const playerModal = page.locator(".ant-modal").filter({ hasText: "新增玩家" });
  await playerModal.getByLabel("玩家称呼").fill(playerName);
  await playerModal.locator(".ant-btn-primary").click();
  await expect(page.getByText(playerName)).toBeVisible();

  let playerPanel = page.locator(".ant-collapse-item").filter({ hasText: playerName });
  await playerPanel.getByRole("button", { name: "添加角色", exact: true }).click();
  const characterModal = page
    .locator(".ant-modal")
    .filter({ hasText: `为 ${playerName} 添加角色` });
  await characterModal.getByLabel("职业").fill("测试职业");
  await characterModal.getByLabel("伤害 / 增益评分").fill("500");
  await characterModal.locator(".ant-btn-primary").click();
  await playerPanel.locator(".ant-collapse-header").click();

  let characterCard = playerPanel.locator(".character-card").filter({
    hasText: "测试职业",
  });
  await expect(characterCard).toBeVisible();
  await characterCard.getByRole("button", { name: "修改" }).click();
  const editCharacterModal = page
    .locator(".ant-modal")
    .filter({ hasText: `修改 ${playerName} 的角色` });
  await editCharacterModal.getByLabel("职业").fill("测试职业改");
  await editCharacterModal.getByLabel("伤害 / 增益评分").fill("600");
  await editCharacterModal.locator(".ant-btn-primary").click();
  characterCard = playerPanel.locator(".character-card").filter({
    hasText: "测试职业改",
  });
  await expect(characterCard.getByText("伤害 · 600.00")).toBeVisible();

  await playerPanel.getByRole("button", { name: "添加角色", exact: true }).click();
  const secondCharacterModal = page
    .locator(".ant-modal")
    .filter({ hasText: `为 ${playerName} 添加角色` });
  await secondCharacterModal.getByLabel("职业").fill("排序职业");
  await secondCharacterModal.getByLabel("伤害 / 增益评分").fill("400");
  await secondCharacterModal.locator(".ant-btn-primary").click();
  const secondCharacterHandle = playerPanel.getByRole("button", {
    name: "拖动角色 排序职业",
  });
  await reorderByKeyboard(page, secondCharacterHandle, "ArrowLeft");
  await expect(page.getByText("角色顺序已保存")).toBeVisible();

  await page.reload();
  await page.getByRole("menuitem", { name: "人员管理" }).click();
  playerPanel = page.locator(".ant-collapse-item").filter({ hasText: playerName });
  await playerPanel.locator(".ant-collapse-header").click();
  await expect(playerPanel.locator(".character-card").first()).toContainText(
    "排序职业",
  );
  characterCard = playerPanel.locator(".character-card").filter({
    hasText: "测试职业改",
  });

  await page.getByRole("button", { name: "新增玩家" }).click();
  const secondPlayerModal = page.locator(".ant-modal").filter({ hasText: "新增玩家" });
  await secondPlayerModal.getByLabel("玩家称呼").fill(secondPlayerName);
  await secondPlayerModal.locator(".ant-btn-primary").click();
  const secondPlayerHandle = page.getByRole("button", {
    name: `拖动玩家 ${secondPlayerName}`,
    exact: true,
  });
  await reorderByKeyboard(page, secondPlayerHandle, "ArrowUp");
  await expect(page.getByText("玩家顺序已保存")).toBeVisible();

  await page.reload();
  await page.getByRole("menuitem", { name: "人员管理" }).click();
  await expect(page.locator(".sortable-player").first()).toContainText(
    secondPlayerName,
  );
  playerPanel = page.locator(".ant-collapse-item").filter({ hasText: playerName });
  await playerPanel.locator(".ant-collapse-header").click();
  characterCard = playerPanel.locator(".character-card").filter({
    hasText: "测试职业改",
  });

  await characterCard.getByRole("button", { name: "停用" }).click();
  const characterConfirm = page
    .locator(".ant-modal-confirm")
    .filter({ hasText: "停用角色“测试职业改”？" });
  await characterConfirm.getByRole("button", { name: "确认停用" }).click();
  await expect(characterCard.getByText("已停用")).toBeVisible();

  await playerPanel
    .locator(".ant-collapse-header")
    .getByRole("button", { name: "修改" })
    .click();
  const editPlayerModal = page.locator(".ant-modal").filter({ hasText: "修改玩家" });
  await editPlayerModal.getByLabel("玩家称呼").fill(updatedPlayerName);
  await editPlayerModal.locator(".ant-btn-primary").click();
  playerPanel = page
    .locator(".ant-collapse-item")
    .filter({ hasText: updatedPlayerName });
  await expect(playerPanel).toBeVisible();

  await playerPanel
    .locator(".ant-collapse-header")
    .getByRole("button", { name: "停用" })
    .click();
  const playerConfirm = page
    .locator(".ant-modal-confirm")
    .filter({ hasText: `停用玩家“${updatedPlayerName}”？` });
  await playerConfirm.getByRole("button", { name: "确认停用" }).click();
  await expect(
    playerPanel.locator(".ant-collapse-header").getByText("已停用"),
  ).toBeVisible();
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
  await expect(page.getByText(/12 波 · 修订 1/)).toBeVisible();

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
