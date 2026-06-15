import { test, expect } from "@playwright/test";

test.describe("Full participant flow", () => {
  test("home → consent → pre-survey → practice case → formal case → post-survey → completion", async ({
    page,
  }) => {
    // 1. Home page renders with CTA
    await page.goto("/");
    await expect(page.locator("text=欢迎参与本研究")).toBeVisible();
    await expect(page.locator("text=15–20 分钟")).toBeVisible();

    // 2. Start study → consent
    await page.click("text=开始研究");
    await expect(page).toHaveURL(/\/consent/);
    await expect(page.locator("text=知情同意")).toBeVisible();

    // 3. Agree → pre-survey
    await page.click("text=我同意 — 开始");
    await expect(page).toHaveURL(/\/pre-survey/, { timeout: 15_000 });

    // 4. Fill pre-survey (5 questions)
    await page.selectOption("select", { index: 1 }); // specialty
    await page.waitForTimeout(200);

    // Select remaining fields via generic selects
    const selects = await page.locator("select").all();
    for (const sel of selects.slice(1)) {
      const opts = await sel.locator("option").all();
      if (opts.length > 1) await sel.selectOption({ index: 1 });
    }

    // Submit pre-survey
    await page.click("text=继续");
    await expect(page).toHaveURL(/\/practice/, { timeout: 15_000 });

    // 5. Practice case — select send_as_is
    await expect(page.locator("text=练习案例")).toBeVisible();
    await page.click("text=原样发送");
    await page.waitForTimeout(300);

    // Click save and continue (may need scrolling)
    const saveBtn = page.locator("text=保存并继续").first();
    if (await saveBtn.isVisible()) await saveBtn.click();
    await page.waitForTimeout(500);

    // Quick survey after practice case
    const confirmBtn = page.locator("text=确认并继续").first();
    if (await confirmBtn.isVisible()) {
      // Select Likert = 3 for confidence
      const likertBtns = await page.locator('[role="radiogroup"] button').all();
      if (likertBtns.length >= 3) await likertBtns[2].click();
      await page.waitForTimeout(200);
      if (likertBtns.length >= 6) await likertBtns[5].click(); // helpfulness
      await page.waitForTimeout(200);
      // Select reason
      const reasonRadios = await page.locator('input[type="radio"]').all();
      if (reasonRadios.length > 0) await reasonRadios[0].check();
      await page.waitForTimeout(200);
      await confirmBtn.click();
    }

    await page.waitForTimeout(1000);

    // 6. Should be on a formal case page (case number, not practice)
    const currentUrl = page.url();
    expect(/\/case\/|\/completion|\/post-survey/.test(currentUrl)).toBeTruthy();

    // If we landed on a formal case page, go through one full case
    if (/\/case\//.test(currentUrl)) {
      // Verify the formal case heading is visible (case number, not "练习")
      await expect(page.locator("text=案例")).toBeVisible();

      // Select an action — edit_then_send is a safe default
      await page.click("text=编辑后发送");
      await page.waitForTimeout(300);

      // Fill in the final reply (textarea should be pre-filled or writable)
      const textarea = page.locator("textarea").first();
      if (await textarea.isVisible()) {
        // Ensure there's some content (AI draft is usually pre-filled)
        const value = await textarea.inputValue();
        if (value.trim() === "") {
          await textarea.fill("根据患者情况，建议休息并多喝水，如有加重请及时就诊。");
        }
      }

      // Save and continue
      const saveBtn2 = page.locator("text=保存并继续").first();
      if (await saveBtn2.isVisible()) await saveBtn2.click();
      await page.waitForTimeout(500);

      // Quick survey after formal case
      const confirmBtn2 = page.locator("text=确认并继续").first();
      if (await confirmBtn2.isVisible()) {
        const likertBtns2 = await page
          .locator('[role="radiogroup"] button')
          .all();
        if (likertBtns2.length >= 3) await likertBtns2[2].click();
        await page.waitForTimeout(200);
        if (likertBtns2.length >= 6) await likertBtns2[5].click();
        await page.waitForTimeout(200);
        const reasonRadios2 = await page.locator('input[type="radio"]').all();
        if (reasonRadios2.length > 0) await reasonRadios2[0].check();
        await page.waitForTimeout(200);
        await confirmBtn2.click();
      }

      await page.waitForTimeout(1000);

      // 7. After first formal case, should be on next case, post-survey, or completion
      const afterCaseUrl = page.url();
      expect(
        /\/case\/|\/post-survey|\/completion/.test(afterCaseUrl),
      ).toBeTruthy();

      // If we hit the post-survey page, verify it loads
      if (/\/post-survey/.test(afterCaseUrl)) {
        // Verify post-survey heading is visible
        const postSurveyHeading = page.locator(
          "text=问卷, text=调查, text=后测",
        );
        await expect(postSurveyHeading.first()).toBeAttached({ timeout: 5_000 });
      }
    }
  });

  test("admin login page shows login form when no token", async ({ page }) => {
    await page.goto("/admin");
    await expect(page.locator("text=管理员登录")).toBeVisible();
    await expect(page.locator("#admin-token")).toBeVisible();
  });
});
