import { expect, test, type Page } from "@playwright/test";

import {
  apiUrl,
  createWrongParkingReport,
  deleteWrongParkingReport,
  slotButton,
  type E2eWrongParkingReport,
} from "./helpers";

async function openReportDrawer(page: Page, slotId: string, count: number) {
  const slot = slotButton(page, slotId);
  await expect(slot).toHaveClass(/has-open-reports/);
  await expect(slot.locator(".map-slot-report-warning b")).toHaveText(String(count));
  await slot.click();
  await expect(page.getByRole("dialog", { name: /Ô [A-D]\d{2}/ })).toBeVisible();
  return slot;
}

function reportCard(page: Page, reportId: string) {
  return page.locator(`[data-report-id="${reportId}"]`);
}

async function resolveReport(
  page: Page,
  report: E2eWrongParkingReport,
  outcome: Exclude<
    E2eWrongParkingReport["verification_outcome"],
    "PENDING"
  > = "CONFIRMED",
) {
  const card = reportCard(page, report.id);
  await expect(card).toBeVisible();
  await card.getByLabel(/Kết quả xác minh/).selectOption(outcome);
  await card.getByRole("button", { name: "Resolve report" }).click();
  await expect(card.getByRole("button", { name: "Reopen report" })).toBeVisible();
  return { ...report, status: "RESOLVED" as const, version: report.version + 1 };
}

test("admin resolves the last OPEN report and removes the slot warning", async ({
  page,
}) => {
  const created = await createWrongParkingReport(page, "F1-C02");
  expect(created.reward_points).toBe(20);
  expect(created.reward_status).toBe("PENDING");
  await page.goto("/admin");

  const slot = await openReportDrawer(page, created.slot_id, 1);
  const resolved = await resolveReport(page, created);
  await expect(slot).not.toHaveClass(/has-open-reports/);

  const detail = await page.request.get(`${apiUrl}/admin/reports/${created.id}`);
  expect(detail.status()).toBe(200);
  const resolvedDetail = ((await detail.json()) as { data: E2eWrongParkingReport })
    .data;
  expect(resolvedDetail).toMatchObject({
    status: "RESOLVED",
    verification_outcome: "CONFIRMED",
    reward_status: "EARNED",
  });
  const summary = await page.request.get(`${apiUrl}/rewards/users/USER-001/summary`);
  expect((await summary.json()).data.available_points).toBeGreaterThanOrEqual(20);
  await deleteWrongParkingReport(page, resolved);
});

test("two OPEN reports keep the warning until both are resolved", async ({ page }) => {
  const first = await createWrongParkingReport(page, "F1-C03");
  const second = await createWrongParkingReport(page, "F1-C03");
  expect(first.reward_points).toBe(20);
  expect(second).toMatchObject({
    reward_points: 0,
    reward_status: null,
    duplicate_candidate_of_id: first.id,
  });
  await page.goto("/admin");

  const slot = await openReportDrawer(page, first.slot_id, 2);
  const firstResolved = await resolveReport(page, first);
  await expect(slot).toHaveClass(/has-open-reports/);
  await expect(slot.locator(".map-slot-report-warning b")).toHaveText("1");

  const secondResolved = await resolveReport(page, second, "DUPLICATE");
  await expect(slot).not.toHaveClass(/has-open-reports/);
  await expect(slot.locator(".map-slot-report-warning")).toHaveCount(0);

  await deleteWrongParkingReport(page, firstResolved);
  await deleteWrongParkingReport(page, secondResolved);
});

test("a rejected report cancels its reward without changing the slot", async ({
  page,
}) => {
  const before = await page.request.get(`${apiUrl}/parking/slots/F1-C05`);
  const beforeStatus = (await before.json()).data.status as string;
  const created = await createWrongParkingReport(page, "F1-C05");
  expect(created.reward_status).toBe("PENDING");
  await page.goto("/admin");

  await openReportDrawer(page, created.slot_id, 1);
  const resolved = await resolveReport(page, created, "REJECTED");
  const detail = await page.request.get(`${apiUrl}/admin/reports/${created.id}`);
  expect(((await detail.json()) as { data: E2eWrongParkingReport }).data).toMatchObject({
    verification_outcome: "REJECTED",
    reward_status: "CANCELLED",
  });
  const after = await page.request.get(`${apiUrl}/parking/slots/F1-C05`);
  expect((await after.json()).data.status).toBe(beforeStatus);
  await deleteWrongParkingReport(page, resolved);
});

test("hard delete requires confirmation and GET returns 404 afterward", async ({
  page,
}) => {
  const created = await createWrongParkingReport(page, "F1-C04");
  await page.goto("/admin");
  const slot = await openReportDrawer(page, created.slot_id, 1);
  const card = reportCard(page, created.id);

  await card.getByRole("button", { name: "Xóa vĩnh viễn" }).click();
  const confirmation = page.getByRole("alertdialog", {
    name: "Xóa vĩnh viễn report?",
  });
  await expect(confirmation).toContainText(created.id);
  await expect(confirmation).toContainText("Ô C04");
  await confirmation.getByRole("button", { name: "Hủy" }).click();
  expect((await page.request.get(`${apiUrl}/admin/reports/${created.id}`)).status()).toBe(
    200,
  );

  await card.getByRole("button", { name: "Xóa vĩnh viễn" }).click();
  await confirmation
    .getByRole("button", { name: "Xác nhận xóa vĩnh viễn" })
    .click();
  await expect(card).toHaveCount(0);
  await expect(slot).not.toHaveClass(/has-open-reports/);

  const missing = await page.request.get(`${apiUrl}/admin/reports/${created.id}`);
  expect(missing.status()).toBe(404);
  expect((await missing.json()) as { error: { code: string } }).toMatchObject({
    error: { code: "REPORT_NOT_FOUND" },
  });
});
