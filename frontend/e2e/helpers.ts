import { expect, type Page } from "@playwright/test";

export const apiUrl =
  process.env.E2E_API_URL ?? "http://127.0.0.1:8100/api/v1";

export interface E2eWrongParkingReport {
  id: string;
  slot_id: string;
  status: "OPEN" | "RESOLVED";
  verification_outcome:
    | "PENDING"
    | "CONFIRMED"
    | "REJECTED"
    | "DUPLICATE"
    | "UNVERIFIABLE";
  reward_points: number;
  reward_status: "PENDING" | "EARNED" | "CANCELLED" | null;
  duplicate_candidate_of_id: string | null;
  version: number;
}

interface SuccessEnvelope<T> {
  success: true;
  data: T;
}

export function slotButton(page: Page, slotId: string) {
  return page.getByRole("button", {
    name: new RegExp(`^Ô đỗ ${slotId},`),
  });
}

export async function createWrongParkingReport(
  page: Page,
  slotId: string,
): Promise<E2eWrongParkingReport> {
  const response = await page.request.post(`${apiUrl}/reports/wrong-parking`, {
    data: {
      user_id: "USER-001",
      slot_id: slotId,
      reason_code: "CROSSED_LINE",
      observed_plate_number: null,
      description: null,
    },
  });
  expect(response.status()).toBe(201);
  const envelope = (await response.json()) as SuccessEnvelope<E2eWrongParkingReport>;
  return envelope.data;
}

export async function deleteWrongParkingReport(
  page: Page,
  report: E2eWrongParkingReport,
) {
  const response = await page.request.delete(
    `${apiUrl}/admin/reports/${report.id}?expected_version=${report.version}`,
  );
  expect(response.status()).toBe(200);
}

export async function resetDemo(page: Page) {
  const response = await page.request.post(`${apiUrl}/simulator/reset`, {
    data: {},
  });
  expect(response.status()).toBe(200);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Trợ lý ParkSmart" }),
  ).toBeVisible();
}

export async function confirmLocation(page: Page, nodeId: string) {
  await page
    .getByRole("button", { name: /Vị trí hiện tại:/ })
    .click();
  const dialog = page.getByRole("dialog", { name: "Xác nhận vị trí hiện tại" });
  await expect(dialog).toBeVisible();

  const slot = /^(F[1-3])-([A-D])(\d{2})$/.exec(nodeId);
  if (slot) {
    await dialog.getByRole("button", { name: "Tôi đang cạnh một ô đỗ" }).click();
    await dialog
      .getByRole("button", { name: `Tầng ${slot[1].slice(1)}`, exact: true })
      .click();
    await dialog.getByRole("button", { name: `Khu ${slot[2]}` }).click();
    await dialog
      .getByRole("button", {
        name: `Chọn ô ${slot[3]} khu ${slot[2]}, tầng ${slot[1].slice(1)}`,
      })
      .click();
  } else {
    await dialog.getByRole("button", { name: new RegExp(nodeId) }).click();
  }

  await expect(dialog).toBeHidden();
  await expect(
    page.getByRole("button", { name: /Vị trí hiện tại:/ }),
  ).toContainText(nodeId);
}

export async function requestCandidate(page: Page) {
  await page.getByRole("button", { name: /^Tìm ô đỗ$/ }).click();
  const candidate = page
    .getByRole("group", { name: "Thao tác cho câu trả lời này" })
    .getByRole("button", { name: /^Chọn ô/ })
    .first();
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
  expect(body.data.path.length).toBeGreaterThan(1);
  return body.data;
}
