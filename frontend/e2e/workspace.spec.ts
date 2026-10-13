import { test, expect } from "@playwright/test";
import path from "node:path";
import { readFileSync } from "node:fs";

test("course → real formats → bilingual search → source locator, theme and narrow layout", async ({
  page,
}) => {
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
  await page.getByLabel("选择资料文件", { exact: true }).setInputFiles([
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
  const result = page
    .locator(".search-result")
    .filter({ hasText: suffix })
    .getByRole("link");
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
  await expect
    .poll(async () => (await page.locator(".sidebar").boundingBox())?.x ?? 0)
    .toBeLessThanOrEqual(-243);
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

test("source note → local Mock AI citations → manual review → four quiz types → backup restore", async ({
  page,
}, testInfo) => {
  const suffix = Date.now().toString();
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "我的课程" })
    .click();
  await page.getByRole("button", { name: "新建课程" }).click();
  await page
    .getByLabel("课程名称", { exact: true })
    .fill("Study Flow " + suffix);
  await page.getByRole("button", { name: "保存课程" }).click();
  await page
    .locator("article")
    .filter({ hasText: "Study Flow " + suffix })
    .getByRole("link", { name: "进入课程" })
    .click();
  await page.getByLabel("选择资料文件", { exact: true }).setInputFiles({
    name: "study-" + suffix + ".md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      "# Gradient descent\n梯度下降使用导数更新参数。Probability is between zero and one. " +
        suffix,
    ),
  });
  await expect(page.getByText("已索引", { exact: true })).toHaveCount(1);
  await page
    .locator(".document-row")
    .filter({ hasText: "study-" + suffix + ".md" })
    .getByRole("link", { name: /打开/ })
    .click();
  await page.getByRole("button", { name: "创建引用笔记" }).click();
  await page.getByLabel("笔记标题").fill("Course Note " + suffix);
  await page
    .getByLabel("Markdown 内容")
    .fill(
      "# 我的理解\n\n梯度下降用导数。$x^2$\n\n| 概念 | 含义 |\n|---|---|\n| gradient | 梯度 |",
    );
  await page.getByRole("button", { name: "保存笔记" }).click();
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();
  await expect(page.locator(".note-preview .katex")).toBeVisible();
  await expect(
    page.locator(".note-connections .citation-card a").first(),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("笔记标题")).toHaveValue(
    "Course Note " + suffix,
  );
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "设置", exact: true })
    .click();
  await page
    .getByLabel("服务地址", { exact: true })
    .fill("http://127.0.0.1:18765/v1");
  await page.getByLabel("聊天模型", { exact: true }).fill("mock-academic-test");
  await page
    .getByLabel("Embedding 模型", { exact: true })
    .fill("mock-embedding-test");
  await page.getByRole("button", { name: "保存并检测连接" }).click();
  await expect(page.getByRole("status")).toContainText("连接成功");
  await page
    .getByRole("button", { name: "构建 / 重建 Embedding 索引" })
    .click();
  await expect(page.locator(".embedding-status")).toContainText("done", {
    timeout: 15000,
  });
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "AI 学术问答" })
    .click();
  await page.getByRole("button", { name: "新建对话" }).click();
  await page.getByLabel("对话标题").fill("Cited Study " + suffix);
  await page
    .getByLabel("课程范围")
    .selectOption({ label: "Study Flow " + suffix });
  await page.getByRole("button", { name: "创建对话", exact: true }).click();
  await page.getByLabel("向资料提问").fill("梯度下降");
  await page.getByRole("button", { name: "发送问题" }).click();
  await expect(page.locator(".answer-status")).toContainText("引用已核验");
  await page.locator(".message.assistant details summary").first().click();
  await expect(
    page.getByRole("link", { name: "打开实际来源 →" }),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "练习与复习" })
    .click();
  await page
    .getByLabel("学习课程")
    .selectOption({ label: "Study Flow " + suffix });
  await page.getByRole("button", { name: "新建卡片" }).click();
  await page.getByLabel("卡片正面").fill("什么是梯度？ " + suffix);
  await page.getByLabel("卡片背面").fill("偏导数组成的向量。");
  await page.getByRole("button", { name: "保存卡片" }).click();
  await page.getByRole("button", { name: "开始到期复习" }).click();
  await page.getByRole("button", { name: "显示答案" }).click();
  await expect(page.locator(".review-answer")).toContainText(
    "偏导数组成的向量",
  );
  await page.getByRole("button", { name: "记得", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("已记录复习");
  await page.getByRole("tab", { name: "Quiz 练习" }).click();
  await page.getByRole("button", { name: "新建练习" }).click();
  await page.getByLabel("练习标题").fill("Four Types " + suffix);
  await page.getByLabel("第 1 题题干").fill("概率的取值范围？");
  await page.getByLabel("第 1 题选项").fill("0 到 1\n任意实数");
  await page.getByRole("button", { name: "添加题目" }).click();
  await page.getByLabel("第 2 题题型").selectOption("multiple");
  await page.getByLabel("第 2 题题干").fill("选择数学对象。");
  await page.getByLabel("第 2 题选项").fill("向量\n矩阵\n普通单词");
  await page
    .locator(".question-editor")
    .nth(1)
    .getByRole("checkbox", { name: /矩阵/ })
    .check();
  await page.getByRole("button", { name: "添加题目" }).click();
  await page.getByLabel("第 3 题题型").selectOption("short");
  await page.getByLabel("第 3 题题干").fill("解释梯度。");
  await page
    .locator(".question-editor")
    .nth(2)
    .getByLabel("参考答案", { exact: true })
    .fill("偏导数向量");
  await page.getByRole("button", { name: "添加题目" }).click();
  await page.getByLabel("第 4 题题型").selectOption("math");
  await page.getByLabel("第 4 题题干").fill("计算 $1+1$。");
  await page
    .locator(".question-editor")
    .nth(3)
    .getByLabel("参考答案", { exact: true })
    .fill("2");
  await page.getByRole("button", { name: "保存练习" }).click();
  await page
    .locator("article")
    .filter({ hasText: "Four Types " + suffix })
    .getByRole("button", { name: "开始作答 →" })
    .click();
  await page.getByRole("radio", { name: /0 到 1/ }).check();
  await page.getByRole("checkbox", { name: /向量/ }).check();
  await page.getByRole("checkbox", { name: /矩阵/ }).check();
  for (const index of [2, 3]) {
    await page
      .getByLabel(`第 ${index + 1} 题作答`)
      .fill(index === 2 ? "偏导数向量" : "2");
    await page
      .locator(".question-card")
      .nth(index)
      .getByRole("button", { name: "查看参考答案并自评" })
      .click();
    await page
      .locator(".question-card")
      .nth(index)
      .getByRole("button", { name: "我答对了" })
      .click();
  }
  await page.getByRole("button", { name: "提交答题" }).click();
  await expect(
    page.getByText(
      "本次得分 4 / 4。选择题按答案判分；简答和数学题记录你的自评。",
    ),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "设置", exact: true })
    .click();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载完整备份" }).click();
  const backup = await downloaded;
  const backupPath = testInfo.outputPath("library-backup.zip");
  await backup.saveAs(backupPath);
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "我的课程" })
    .click();
  await page.getByRole("button", { name: "新建课程" }).click();
  await page
    .getByLabel("课程名称", { exact: true })
    .fill("After Backup " + suffix);
  await page.getByRole("button", { name: "保存课程" }).click();
  await expect(
    page.getByRole("heading", { name: "After Backup " + suffix }),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "设置", exact: true })
    .click();
  await page.getByLabel("选择恢复备份").setInputFiles(backupPath);
  await page.getByLabel("输入 RESTORE 确认替换").fill("RESTORE");
  await page.getByRole("button", { name: "恢复知识库", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("恢复完成", {
    timeout: 15000,
  });
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "我的课程" })
    .click();
  await expect(
    page.getByRole("heading", { name: "After Backup " + suffix }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Study Flow " + suffix }),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "练习与复习" })
    .click();
  await page.getByRole("tab", { name: "进度与错题" }).click();
  await expect(
    page.getByText("Four Types " + suffix, { exact: false }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("study-history.png"),
    fullPage: true,
  });
});

test("folder and drop imports → Office/PDF locators → multiple note sources and link choice → generated drafts → portable merge", async ({
  page,
}, testInfo) => {
  test.setTimeout(60000);
  const suffix = Date.now().toString();
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "我的课程" })
    .click();
  await page.getByRole("button", { name: "新建课程" }).click();
  await page.getByLabel("课程名称", { exact: true }).fill("Advanced " + suffix);
  await page.getByRole("button", { name: "保存课程" }).click();
  await page
    .locator("article")
    .filter({ hasText: "Advanced " + suffix })
    .getByRole("link", { name: "进入课程" })
    .click();
  const courseId = new URLSearchParams(
    new URL(page.url()).hash.split("?")[1],
  ).get("course")!;
  await page
    .getByLabel("选择资料文件夹")
    .setInputFiles(path.resolve("../var/demo"));
  await expect(page.getByText("已索引", { exact: true })).toHaveCount(5, {
    timeout: 20000,
  });
  const transfer = await page.evaluateHandle((suffix) => {
    const data = new DataTransfer();
    data.items.add(
      new File(
        ["# Drag material " + suffix + "\nGradient descent and 梯度下降."],
        "drag-" + suffix + ".md",
        { type: "text/markdown" },
      ),
    );
    return data;
  }, suffix);
  await page
    .locator(".dropzone")
    .dispatchEvent("drop", { dataTransfer: transfer });
  await expect(page.getByText("已索引", { exact: true })).toHaveCount(6);
  const docs = await (
    await page.request.get("/api/v1/documents?course_id=" + courseId)
  ).json();
  const pdf = docs.find((d: any) => d.kind === "pdf"),
    ppt = docs.find((d: any) => d.kind === "pptx"),
    docx = docs.find((d: any) => d.kind === "docx");
  for (const [doc, label] of [
    [pdf, "页 2"],
    [docx, "段落 / 表格 2"],
  ] as const) {
    await page.goto("/#/documents/" + doc.id + "?locator=2");
    await expect(page.locator(".source-unit .pill")).toHaveText(label);
    await expect(page.locator(".source-unit pre")).not.toBeEmpty();
  }
  await page.goto("/#/documents/" + ppt.id + "?locator=1");
  await expect(page.locator(".source-unit .pill")).toHaveText("幻灯片 1");
  await expect(page.locator(".slide-images img")).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator(".slide-images img")
        .evaluate(
          (img: HTMLImageElement) => img.complete && img.naturalWidth > 0,
        ),
    )
    .toBeTruthy();
  await page.screenshot({
    path: testInfo.outputPath("slide-preview.png"),
    fullPage: true,
  });
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "学习笔记" })
    .click();
  const targetIds: string[] = [];
  for (const body of ["First concept note", "Second concept note"]) {
    await page.getByRole("button", { name: "新建笔记" }).click();
    await page.getByLabel("笔记标题").fill("Same " + suffix);
    await page.getByLabel("Markdown 内容").fill(body);
    await page.getByRole("button", { name: "保存笔记" }).click();
    await expect(page.getByText("已保存", { exact: true })).toBeVisible();
    await expect(page).toHaveURL(/id=/);
    targetIds.push(
      new URLSearchParams(new URL(page.url()).hash.split("?")[1]).get("id")!,
    );
  }
  await page.getByRole("button", { name: "新建笔记" }).click();
  await page.getByLabel("笔记标题").fill("Connected " + suffix);
  await page
    .getByLabel("Markdown 内容")
    .fill("[[Same " + suffix + "]]\n\n跨资料总结。");
  for (const document of [pdf, docx]) {
    await page
      .getByRole("button", { name: "添加资料引用", exact: true })
      .click();
    await page
      .getByLabel("选择资料", { exact: true })
      .selectOption(document.id);
    await expect(
      page.getByLabel("选择原文位置").locator("option"),
    ).not.toHaveCount(1);
    await page.getByLabel("选择原文位置").selectOption({ index: 1 });
    await page.getByRole("button", { name: "添加此引用" }).click();
  }
  await page.getByRole("button", { name: "保存笔记" }).click();
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();
  await expect(page.locator(".note-connections .citation-card")).toHaveCount(2);
  await page
    .getByLabel("为 [[Same " + suffix + "]] 选择目标笔记")
    .selectOption(targetIds[1]);
  await page
    .getByRole("button", { name: "确认链接 [[Same " + suffix + "]]" })
    .click();
  await expect(
    page.getByLabel("为 [[Same " + suffix + "]] 选择目标笔记"),
  ).toHaveCount(0);
  await expect(page.locator(".links-grid a").first()).toHaveAttribute(
    "href",
    "#/notes?id=" + targetIds[1],
  );
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "知识搜索" })
    .click();
  await page.getByLabel("搜索内容类型").selectOption("notes");
  await page.getByRole("searchbox").fill("Connected " + suffix);
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Connected " + suffix }),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "设置", exact: true })
    .click();
  await page
    .getByLabel("服务地址", { exact: true })
    .fill("http://127.0.0.1:18765/v1");
  await page.getByLabel("聊天模型", { exact: true }).fill("mock-academic-test");
  await page.getByRole("button", { name: "保存并检测连接" }).click();
  await expect(page.getByRole("status")).toContainText("连接成功");
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "练习与复习" })
    .click();
  await page.getByLabel("学习课程").selectOption(courseId);
  await page.getByRole("button", { name: "AI 学习草稿" }).click();
  await page.getByLabel("知识主题或复习重点").fill("gradient");
  await page.getByLabel("数量", { exact: true }).fill("1");
  await page.getByRole("button", { name: "生成草稿", exact: true }).click();
  await page.getByRole("button", { name: "核对并保存" }).click();
  await page.getByRole("button", { name: "保存卡片" }).click();
  await expect(page.locator(".flashcard-tile")).toHaveCount(1);
  await page.getByRole("button", { name: "AI 学习草稿" }).click();
  await page.getByLabel("生成内容").selectOption("quiz");
  await page.getByLabel("知识主题或复习重点").fill("gradient");
  await page.getByLabel("数量", { exact: true }).fill("1");
  await page.getByRole("button", { name: "生成草稿", exact: true }).click();
  await expect(page.getByLabel("练习标题")).toHaveValue("模拟资料练习");
  await page.getByRole("button", { name: "保存练习" }).click();
  await expect(
    page.getByRole("heading", { name: "模拟资料练习", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "AI 学习草稿" }).click();
  await page.getByLabel("生成内容").selectOption("summary");
  await page.getByLabel("知识主题或复习重点").fill("gradient");
  await page.getByRole("button", { name: "生成草稿", exact: true }).click();
  await page.getByRole("button", { name: "保存为笔记" }).click();
  await expect(page.getByRole("status")).toContainText("总结已保存");
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "设置", exact: true })
    .click();
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("link", { name: "导出便携数据" }).click();
  const archive = testInfo.outputPath("portable.zip");
  await (await downloadEvent).saveAs(archive);
  const before = await (await page.request.get("/api/v1/courses")).json();
  await page.getByLabel("选择便携数据包").setInputFiles(archive);
  await page.getByRole("button", { name: "预览导入内容" }).click();
  await expect(page.getByRole("heading", { name: "导入预览" })).toBeVisible();
  expect(
    (await (await page.request.get("/api/v1/courses")).json()).length,
  ).toBe(before.length);
  await page.getByRole("button", { name: "确认合并导入" }).click();
  await expect(page.getByRole("status")).toContainText("合并导入完成", {
    timeout: 20000,
  });
  expect(
    (await (await page.request.get("/api/v1/courses")).json()).length,
  ).toBe(before.length * 2);
  await page.screenshot({
    path: testInfo.outputPath("data-settings.png"),
    fullPage: true,
  });
});
