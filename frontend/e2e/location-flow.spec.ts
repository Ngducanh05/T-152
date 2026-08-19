import { expect, test } from "@playwright/test";

import { confirmLocation, resetDemo } from "./helpers";

test("confirms checkpoint and slot locations through tap choices without parking", async ({
  page,
}) => {
  const confirmParkingRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith("/sessions/confirm-parking")) {
      confirmParkingRequests.push(request.url());
    }
  });

  await page.goto("/");
  await resetDemo(page);
  await confirmLocation(page, "F1-CP3");
  await confirmLocation(page, "F1-D01");

  await expect(
    page.getByRole("button", { name: /Vị trí hiện tại:/ }),
  ).toContainText("F1-D01");
  await expect(page.getByRole("article", { name: "Xe đang đỗ trong bãi" })).toHaveCount(0);
  expect(confirmParkingRequests).toEqual([]);
});
