import { expect, test } from "@playwright/test";

test("báo cáo mới tự động xuất hiện cho quản trị viên mà không tải lại trang", async ({
  context,
}) => {
  const description = "Xe đỗ chéo và lấn sang ô bên cạnh trong bài kiểm thử.";
  const adminPage = await context.newPage();
  await adminPage.goto("/admin");
  await expect(
    adminPage.getByRole("heading", { name: "Bảng điều khiển vận hành" }),
  ).toBeVisible();

  const page = await context.newPage();

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Tìm chỗ đỗ phù hợp" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Báo xe đỗ sai" }).click();

  const dialog = page.getByRole("dialog", { name: "Báo xe đỗ sai vị trí" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Ô cần phản ánh").selectOption("F1-D01");
  await dialog
    .getByLabel("Biển số hoặc mã xe quan sát được (không bắt buộc)")
    .fill("51a-888.88");
  await dialog.getByLabel(/Mô tả tình trạng/).fill(description);

  const reportResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/reports/wrong-parking") &&
      response.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "Gửi báo cáo" }).click();
  expect((await reportResponse).status()).toBe(201);
  await expect(dialog.getByRole("status")).toContainText("Đã gửi báo cáo");

  await adminPage.bringToFront();
  await expect(adminPage.locator(".admin-report-list")).toContainText(description, {
    timeout: 6_000,
  });
  await expect(adminPage.locator(".admin-report-list")).toContainText("51A-888.88");
  await expect(adminPage.locator(".admin-report-list")).toContainText("F1-D01");
});
