import { expect, type Page } from "@playwright/test";

export const apiUrl =
  process.env.E2E_API_URL ?? "http://127.0.0.1:8100/api/v1";

export function slotButton(page: Page, slotId: string) {
  return page.getByRole("button", {
    name: new RegExp(`^Parking slot ${slotId},`),
  });
}

export async function expectParkingCounts(
  page: Page,
  available: number,
  reserved: number,
  occupied: number,
) {
  const summary = page.getByLabel("Parking status summary");
  await expect(summary.getByLabel("Available slots")).toContainText(
    String(available),
  );
  await expect(summary.getByLabel("Reserved slots")).toContainText(
    String(reserved),
  );
  await expect(summary.getByLabel("Occupied slots")).toContainText(
    String(occupied),
  );
}

export async function resetDemo(page: Page) {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/simulator/reset") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Đặt lại demo" }).click();
  expect((await responsePromise).status()).toBe(200);
  await expect(page.getByRole("button", { name: /^Parking slot / })).toHaveCount(
    40,
  );
  await expectParkingCounts(page, 39, 0, 1);
}

export async function confirmLocation(page: Page, nodeId: string) {
  await page
    .getByRole("button", { name: /Vị trí đã xác nhận/ })
    .click();
  const dialog = page.getByRole("dialog", { name: "Chọn vị trí canonical" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: nodeId, exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(
    page.getByRole("button", { name: /Vị trí đã xác nhận/ }),
  ).toContainText(nodeId);
}

export async function requestCandidate(page: Page) {
  await expect(
    page.getByRole("button", { name: /Cần sạc EV/ }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByRole("button", { name: /Gần thang máy/ }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: /Yêu cầu đề xuất/ }).click();
  const candidates = page.getByLabel("Các ô được đề xuất");
  const candidate = candidates.getByRole("button").first();
  await expect(candidate).toBeVisible();
  const slotId = (await candidate.locator("b").innerText()).trim();
  return { candidate, slotId };
}

export async function waitForRouteResponse(page: Page) {
  const response = await page.waitForResponse(
    (candidate) =>
      candidate.url().includes("/api/v1/routes") &&
      candidate.request().method() === "POST",
  );
  expect(response.status()).toBe(200);
  const body = (await response.json()) as {
    data: { path: string[]; polyline: [number, number][] };
  };
  expect(body.data.polyline.length).toBeGreaterThan(1);
  return body.data;
}
