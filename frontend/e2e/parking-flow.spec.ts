import { expect, test } from "@playwright/test";

import {
  apiUrl,
  confirmLocation,
  expectParkingCounts,
  requestCandidate,
  resetDemo,
  slotButton,
  waitForRouteResponse,
} from "./helpers";

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Tìm chỗ đỗ phù hợp" }),
  ).toBeVisible();
});

test("repeats the deterministic parking happy path three times", async ({
  page,
}) => {
  for (let iteration = 1; iteration <= 3; iteration += 1) {
    await test.step(`happy-path iteration ${iteration}`, async () => {
      await resetDemo(page);
      await confirmLocation(page, "F1-ENTRANCE");

      const { candidate, slotId } = await requestCandidate(page);
      await expectParkingCounts(page, 39, 0, 1);
      await expect(
        page.getByRole("status", { name: "Chỗ đỗ đã giữ", exact: true }),
      ).toHaveCount(0);
      await expect(slotButton(page, slotId)).toHaveAccessibleName(/Đang trống/);

      await candidate.click();
      const reservationResponse = page.waitForResponse(
        (response) =>
          response.url().includes("/api/v1/reservations") &&
          response.request().method() === "POST",
      );
      await page.getByRole("button", { name: "Chọn làm điểm đỗ" }).click();
      expect((await reservationResponse).status()).toBe(201);
      await expect(slotButton(page, slotId)).toHaveAccessibleName(/Đã giữ/);
      await expect(
        page.getByRole("status", { name: "Chỗ đỗ đã giữ", exact: true }),
      ).toContainText(slotId);
      await expectParkingCounts(page, 38, 1, 1);

      const routeResponse = waitForRouteResponse(page);
      await page.getByRole("button", { name: "Chỉ đường", exact: true }).click();
      const route = await routeResponse;
      expect(route.path.at(-1)).toBe(slotId);
      await expect(page.getByTestId("route-polyline")).toBeVisible();
      await expect(page.getByTestId("route-polyline")).not.toHaveAttribute(
        "points",
        "",
      );

      await page.getByRole("button", { name: "Xác nhận đã đỗ" }).click();
      const sessionBanner = page.getByRole("status", {
        name: "Xe đang đỗ trong bãi",
        exact: true,
      });
      await expect(sessionBanner).toContainText(slotId);
      await expect(slotButton(page, slotId)).toHaveAccessibleName(/Đã có xe/);
      await expectParkingCounts(page, 38, 0, 2);

      await confirmLocation(page, "F1-CP3");
      const vehicleRouteResponse = waitForRouteResponse(page);
      await sessionBanner
        .getByRole("button", { name: "Chỉ đường tới xe" })
        .click();
      const vehicleRoute = await vehicleRouteResponse;
      expect(vehicleRoute.path.at(-1)).toBe(slotId);
      await expect(page.getByTestId("route-polyline")).toBeVisible();
    });
  }
});

test("refreshes authoritative state after a recommended slot becomes occupied", async ({
  page,
  request,
}) => {
  await resetDemo(page);
  await confirmLocation(page, "F1-ENTRANCE");
  const { candidate, slotId } = await requestCandidate(page);
  await candidate.click();

  await page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/parking/status") &&
      response.request().method() === "GET",
  );
  const simulatorResponse = await request.post(`${apiUrl}/simulator/park`, {
    data: { slot_id: slotId, vehicle_id: "SIM-CAR-99" },
  });
  expect(simulatorResponse.status()).toBe(200);

  const reservationResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/reservations") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Chọn làm điểm đỗ" }).click();
  expect((await reservationResponse).status()).toBe(409);

  const alert = page.locator(".page-alert");
  await expect(alert).toContainText("Ô vừa thay đổi hoặc không còn trống");
  await expect(alert).toContainText("hãy chọn một ô đang trống khác");
  await expect(slotButton(page, slotId)).toHaveAccessibleName(/Đã có xe/);
  await expect(
    page.getByRole("status", { name: "Chỗ đỗ đã giữ", exact: true }),
  ).toHaveCount(0);
});
