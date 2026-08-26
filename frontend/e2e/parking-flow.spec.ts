import { expect, test } from "@playwright/test";

import {
  apiUrl,
  confirmLocation,
  requestCandidate,
  resetDemo,
  slotButton,
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

  await priorityDock.getByRole("button", { name: "Giúp kiểm tra ngay" }).click();
  const question = priorityDock.getByRole("heading", {
    name: /Bạn nhìn giúp ô [A-D]\d{2}/,
  });
  const shortSlotId = (await question.textContent())?.match(/ô ([A-D]\d{2})/)?.[1];
  expect(shortSlotId).toBeTruthy();
  const observedSlotId = `F1-${shortSlotId}`;
  const slotBeforeResponse = await page.request.get(
    `${apiUrl}/parking/slots/${observedSlotId}`,
  );
  const slotBefore = (await slotBeforeResponse.json()) as {
    data: { status: "AVAILABLE" | "OCCUPIED" };
  };
  const observedStatus = slotBefore.data.status === "AVAILABLE" ? "OCCUPIED" : "AVAILABLE";
  const answerButton = priorityDock.getByRole("button", {
    name: observedStatus === "OCCUPIED" ? "Đã có xe" : "Ô đang trống",
  });
  const observationResponse = page.waitForResponse(
    (response) =>
      response.url().includes(`/parking/slots/${observedSlotId}/observation`) &&
      response.request().method() === "POST",
  );
  await answerButton.click();
  const createdResponse = await observationResponse;
  expect(createdResponse.status()).toBe(200);
  const created = (await createdResponse.json()) as {
    data: { id: string; reward_points: number; verification_status: string };
  };
  expect(created.data.verification_status).toBe("PENDING");
  const observedSlotBeforeVerify = await page.request.get(
    `${apiUrl}/parking/slots/${observedSlotId}`,
  );
  expect(
    ((await observedSlotBeforeVerify.json()) as { data: { status: string } }).data.status,
  ).toBe(slotBefore.data.status);

  await page.goto("/admin");
  const contribution = page.locator(
    `.observation-row[data-observation-id="${created.data.id}"]`,
  );
  await expect(contribution).toBeVisible();
  await contribution.click();
  await expect(slotButton(page, observedSlotId)).toHaveClass(/is-selected/);
  await page.getByRole("button", { name: "Xác minh", exact: true }).click();
  await expect(contribution).toHaveCount(0);
  const observedSlotAfterVerify = await page.request.get(
    `${apiUrl}/parking/slots/${observedSlotId}`,
  );
  expect(
    ((await observedSlotAfterVerify.json()) as { data: { status: string } }).data.status,
  ).toBe(observedStatus);
  const summary = await page.request.get(`${apiUrl}/rewards/users/USER-001/summary`);
  expect(
    ((await summary.json()) as { data: { available_points: number } }).data.available_points,
  ).toBeGreaterThanOrEqual(created.data.reward_points);
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
