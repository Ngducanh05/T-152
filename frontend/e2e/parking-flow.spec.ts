import { expect, test } from "@playwright/test";

import {
  apiUrl,
  confirmLocation,
  requestCandidate,
  resetDemo,
  waitForRouteResponse,
} from "./helpers";

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Trợ lý ParkSmart" }),
  ).toBeVisible();
});

test("completes the tap-first parking path without exposing an operational map", async ({
  page,
}) => {
  await resetDemo(page);
  await confirmLocation(page, "F1-ENTRANCE");

  const { candidate, slotId } = await requestCandidate(page);
  await candidate.click();
  const reservationResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/reservations") &&
      response.request().method() === "POST",
  );
  const routeResponse = waitForRouteResponse(page);
  await page.getByRole("button", { name: /Giữ ô và chỉ đường/ }).click();
  expect((await reservationResponse).status()).toBe(201);
  const route = await routeResponse;
  expect(route.path.at(-1)).toBe(slotId);

  await expect(
    page.getByRole("article", { name: "Chỗ đỗ đã giữ" }),
  ).toContainText(slotId);
  const routeCard = page.getByRole("article", { name: "Chỉ đường trong bãi" });
  await expect(routeCard.locator("li")).toHaveCount(route.path.length);
  for (const nodeId of route.path) await expect(routeCard).toContainText(nodeId);
  await expect(routeCard).toContainText(/Rẽ trái|Rẽ phải|Đi thẳng/);
  await expect(page.locator(".api-parking-map, .parking-summary, .sidebar")).toHaveCount(0);

  const arrivalResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/locations/confirm") &&
      response.request().method() === "POST",
  );
  const parkingResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/sessions/confirm-parking") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Tôi đã đến nơi" }).click();
  expect((await arrivalResponse).status()).toBe(200);
  expect((await parkingResponse).status()).toBe(200);
  await expect(
    page.getByRole("article", { name: "Xe đang đỗ trong bãi" }),
  ).toContainText(slotId);
  const priorityDock = page.getByRole("region", {
    name: "Thông tin và thao tác quan trọng",
  });
  await expect(priorityDock).toHaveCSS("position", "sticky");

  const occupiedObservation = priorityDock
    .getByRole("button", { name: /Báo F1-[A-D]\d{2} có xe đỗ/ })
    .first();
  const observedSlotId = (await occupiedObservation.getAttribute("aria-label"))?.match(
    /F1-[A-D]\d{2}/,
  )?.[0];
  expect(observedSlotId).toBeTruthy();
  const observationResponse = page.waitForResponse(
    (response) =>
      response.url().includes(`/parking/slots/${observedSlotId}/observation`) &&
      response.request().method() === "POST",
  );
  await occupiedObservation.click();
  expect((await observationResponse).status()).toBe(200);
  const observedSlot = await page.request.get(
    `${apiUrl}/parking/slots/${observedSlotId}`,
  );
  expect(((await observedSlot.json()) as { data: { status: string } }).data.status).toBe(
    "OCCUPIED",
  );
});

test("does not request a route when the selected slot becomes occupied", async ({
  page,
  request,
}) => {
  await resetDemo(page);
  await confirmLocation(page, "F1-ENTRANCE");
  const { candidate, slotId } = await requestCandidate(page);
  await candidate.click();

  const simulatorResponse = await request.post(`${apiUrl}/simulator/park`, {
    data: { slot_id: slotId, vehicle_id: "SIM-CAR-99" },
  });
  expect(simulatorResponse.status()).toBe(200);
  let routeCalls = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith("/routes")) routeCalls += 1;
  });

  const reservationResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/reservations") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Giữ ô và chỉ đường/ }).click();
  expect((await reservationResponse).status()).toBe(409);
  await expect(page.locator(".conversation-notice")).toContainText(
    "chọn một ô đang trống khác",
  );
  expect(routeCalls).toBe(0);
});
