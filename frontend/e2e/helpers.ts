import { expect, type Page } from "@playwright/test";

export const apiUrl =
  process.env.E2E_API_URL ?? "http://127.0.0.1:8100/api/v1";

export function slotButton(page: Page, slotId: string) {
  return page.getByRole("button", {
    name: new RegExp(`^Ô đỗ ${slotId},`),
  });
}

export async function expectParkingCounts(
  page: Page,
  available: number,
  reserved: number,
  occupied: number,
) {
  const summary = page.getByLabel("Tóm tắt trạng thái bãi xe");
  await expect(summary.getByLabel("Ô đang trống")).toContainText(
    String(available),
  );
  await expect(summary.getByLabel("Ô đã được giữ")).toContainText(
    String(reserved),
  );
  await expect(summary.getByLabel("Ô đã có xe")).toContainText(
    String(occupied),
  );
}

export async function resetDemo(page: Page) {
  const response = await page.request.post(`${apiUrl}/simulator/reset`, {
    data: {},
  });
  expect(response.status()).toBe(200);
  await page.reload();
  await expect(page.getByRole("button", { name: /^Ô đỗ / })).toHaveCount(
    40,
  );
  await expectParkingCounts(page, 39, 0, 1);
}

export async function confirmLocation(page: Page, nodeId: string) {
  await page
    .getByRole("button", { name: /Vị trí của bạn/ })
    .click();
  const dialog = page.getByRole("dialog", { name: "Xác nhận vị trí hiện tại" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: new RegExp(nodeId) }).click();
  await expect(dialog).toBeHidden();
  await expect(
    page.getByRole("button", { name: /Vị trí của bạn/ }),
  ).toContainText(nodeId);
}

export async function requestCandidate(page: Page) {
  await expect(
    page.getByRole("button", { name: /Cần sạc EV/ }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByRole("button", { name: /Gần thang máy/ }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: /Tìm chỗ phù hợp/ }).click();
  const candidates = page.getByLabel("Các ô được đề xuất");
  const candidate = candidates.getByRole("button").first();
  await expect(candidate).toBeVisible();
  const slotId = await candidate.getAttribute("data-slot-id");
  expect(slotId).not.toBeNull();
  return { candidate, slotId: slotId as string };
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
