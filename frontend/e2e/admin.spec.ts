import { expect, test } from "@playwright/test";

import { apiUrl, slotButton } from "./helpers";

test("shows operational data, filters the shared map, and refreshes after a mutation", async ({
  page,
}) => {
  const reset = await page.request.post(`${apiUrl}/simulator/reset`, { data: {} });
  expect(reset.status()).toBe(200);

  await page.goto("/admin");
  await expect(
    page.getByRole("heading", { name: "Bảng điều khiển vận hành" }),
  ).toBeVisible();
  await expect(page.getByText("Quản trị viên thử nghiệm", { exact: false })).toBeVisible();
  await expect(page.locator(".admin-metrics article")).toHaveCount(7);
  await expect(page.locator(".zone-density-grid article")).toHaveCount(4);
  await expect(page.getByTestId("parking-map")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Ô đỗ / })).toHaveCount(40);

  const zoneFilter = page.locator(".admin-filters select").first();
  await zoneFilter.selectOption("D");
  await expect(page.getByRole("button", { name: /^Ô đỗ / })).toHaveCount(10);
  await expect(page.getByText("10 ô phù hợp")).toBeVisible();
  await zoneFilter.selectOption("ALL");

  await page.locator(".admin-operations form select").first().selectOption("F1-A04");
  await page.getByLabel("Mã xe mô phỏng").fill("SIM-CAR-88");
  const parkResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/simulator/park") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Ghi nhận xe đỗ" }).click();

  expect((await parkResponse).status()).toBe(200);
  await expect(page.getByRole("status")).toContainText("SIM-CAR-88");
  await expect(slotButton(page, "F1-A04")).toHaveAccessibleName(/Đã có xe/);
  await expect(page.locator(".admin-event-list")).toContainText("Xe đã đỗ");
  await expect(
    page.getByRole("link", { name: "Về giao diện người dùng" }),
  ).toHaveAttribute("href", "/");
});
