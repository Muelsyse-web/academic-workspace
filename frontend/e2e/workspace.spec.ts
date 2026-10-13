import { test, expect } from "@playwright/test";
import path from "node:path";
import { readFileSync } from "node:fs";

test("course → real formats → bilingual search → source locator, theme and narrow layout", async ({
  page,
}) => {
  page.on("pageerror", (error) => console.log("PAGE ERROR", error.message));
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) console.log("NAV", frame.url());
  });
  const suffix = Date.now().toString();
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "我的课程" })
    .click();
  await page.getByRole("button", { name: "新建课程" }).click();
  await page
    .getByLabel("课程名称", { exact: true })
    .fill("Machine Learning " + suffix);
  await page.getByLabel("课程代码", { exact: true }).fill("COMP3340");
  await page.getByRole("button", { name: "保存课程" }).click();
  const card = page
    .locator("article")
    .filter({ hasText: "Machine Learning " + suffix });
  await expect(card).toBeVisible();
  await card.getByRole("link", { name: "进入课程" }).click();
  await page
    .getByLabel("选择资料文件", { exact: true })
    .setInputFiles([
      {
        name: "lecture-" + suffix + ".md",
        mimeType: "text/markdown",
        buffer: Buffer.from(
          "# Gradient Descent\n梯度下降使用导数优化参数。Gradient descent updates parameters with derivatives. Test " +
            suffix,
        ),
      },
      ...["pdf", "pptx", "docx"].map((kind) => ({
        name: "synthetic-foundations." + kind,
        mimeType: "application/octet-stream",
        buffer: readFileSync(
          path.resolve("../var/demo/synthetic-foundations." + kind),
        ),
      })),
    ]);
  await expect(page.getByText("已索引", { exact: true })).toHaveCount(4, {
    timeout: 20000,
  });
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "知识搜索" })
    .click();
  await page
    .getByLabel("搜索课程")
    .selectOption({ label: "Machine Learning " + suffix });
  await page.getByRole("searchbox").fill("梯度下降");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  const result = page.getByRole("link", { name: "lecture-" + suffix });
  await expect(result).toBeVisible();
  await result.click();
  await expect(page.locator(".source-unit")).toContainText("梯度下降");
  await expect(page.locator(".source-unit")).toContainText("起始行 1");
  await page.getByLabel("外观主题").selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "打开导航" }).click();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "学习概览" })
    .click();
  await expect(
    page.getByRole("heading", { name: "今天，学一点新知识。" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/mobile-overview.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.getByLabel("外观主题").selectOption("light");
  await page.screenshot({
    path: "test-results/desktop-overview.png",
    fullPage: true,
  });
});
