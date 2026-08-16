import { expect, test } from "@playwright/test";

import { resetDemo, slotButton } from "./helpers";

test("confirms checkpoint and slot locations without changing parking state", async ({
  page,
}) => {
  const confirmParkingRequests: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname.endsWith("/sessions/confirm-parking")
    ) {
      confirmParkingRequests.push(request.url());
    }
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Tìm chỗ đỗ phù hợp" })).toBeVisible();
  await resetDemo(page);

  const locationButton = page.getByRole("button", { name: /Vị trí của bạn/ });
  const targetSlot = slotButton(page, "F1-D01");
  await expect(targetSlot).toHaveAccessibleName(/Đang trống/);

  await locationButton.click();
  const checkpointResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname.endsWith("/locations/confirm"),
  );
  await page.getByRole("dialog", { name: "Xác nhận vị trí hiện tại" })
    .getByRole("button", { name: /F1-CP3/ })
    .click();
  expect((await checkpointResponse).status()).toBe(200);
  await expect(locationButton).toContainText("F1-CP3");

  await locationButton.click();
  const dialog = page.getByRole("dialog", { name: "Xác nhận vị trí hiện tại" });
  await dialog.getByRole("combobox", { name: "Tìm ô đỗ theo ID" }).fill("  f1-d01  ");
  const slotResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname.endsWith("/locations/confirm"),
  );
  await dialog.getByRole("button", { name: "Xác nhận vị trí ô đỗ" }).click();
  const confirmedSlotResponse = await slotResponse;
  expect(confirmedSlotResponse.status()).toBe(200);
  expect(confirmedSlotResponse.request().postDataJSON()).toMatchObject({
    node_id: "F1-D01",
  });

  await expect(locationButton).toContainText("F1-D01");
  await expect(targetSlot).toHaveAccessibleName(/Đang trống/);
  await expect(page.getByRole("status", { name: "Kết quả xác nhận vị trí" })).toContainText(
    "Đã cập nhật vị trí hiện tại thành Ô D01 (F1-D01)",
  );
  await expect(page.getByRole("status", { name: "Xe đang đỗ trong bãi" })).toHaveCount(0);
  expect(confirmParkingRequests).toEqual([]);
});
