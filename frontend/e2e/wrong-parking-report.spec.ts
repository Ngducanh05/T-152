import { expect, test } from "@playwright/test";

import { slotButton } from "./helpers";

test("báo cáo mới tự động xuất hiện cho quản trị viên mà không tải lại trang", async ({
  context,
}) => {
  const adminPage = await context.newPage();
  await adminPage.goto("/admin");
  await expect(
    adminPage.getByRole("heading", { name: "Bảng điều khiển vận hành" }),
  ).toBeVisible();

  const page = await context.newPage();

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Trợ lý ParkSmart" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /^Báo xe đỗ sai$/ }).click();

  const dialog = page.getByRole("dialog", { name: "Báo xe đỗ sai vị trí" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Ô cần phản ánh").selectOption("F1-D01");

  const reportResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/reports/wrong-parking") &&
      response.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "Gửi: Xe đỗ chéo vạch" }).click();
  const createdResponse = await reportResponse;
  expect(createdResponse.status()).toBe(201);
  const created = (await createdResponse.json()) as {
    data: { id: string };
  };
  await expect(dialog.getByRole("status")).toContainText("Đã gửi báo cáo");

  await adminPage.bringToFront();
  const warnedSlot = slotButton(adminPage, "F1-D01");
  await expect(warnedSlot).toHaveClass(/has-open-reports/, { timeout: 6_000 });
  await warnedSlot.click();
  await expect(
    adminPage.locator(`[data-report-id="${created.data.id}"]`),
  ).toContainText("Xe đỗ chéo vạch");
});
