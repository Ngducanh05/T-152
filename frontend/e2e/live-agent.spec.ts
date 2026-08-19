import { expect, test } from "@playwright/test";

import { confirmLocation, resetDemo } from "./helpers";

const liveAgentEnabled =
  process.env.RUN_LIVE_AGENT_E2E === "1" && Boolean(process.env.LLM_API_KEY);

test("@live-agent uses the real Agent to recommend and reserve a slot", async ({
  page,
}) => {
  test.skip(
    !liveAgentEnabled,
    "Set RUN_LIVE_AGENT_E2E=1 and LLM_API_KEY to run the live Agent E2E.",
  );

  await page.goto("/");
  await resetDemo(page);
  await confirmLocation(page, "F1-ENTRANCE");

  const input = page.getByRole("textbox", { name: "Tin nhắn cho ParkSmart AI" });
  await input.fill("Hãy đề xuất ô có sạc EV gần thang máy cho tôi.");
  await page.getByRole("button", { name: "Gửi tin nhắn" }).click();
  const recommendedSlot = page
    .getByRole("button", { name: /^Chọn ô/ })
    .first();
  await expect(recommendedSlot).toBeVisible();
  const slotId = await recommendedSlot.getAttribute("data-slot-id");
  expect(slotId).toBeTruthy();

  await input.fill(`Tôi chọn ${slotId}, hãy giữ đúng ô đó cho tôi.`);
  await page.getByRole("button", { name: "Gửi tin nhắn" }).click();
  await expect(
    page.getByRole("article", { name: "Chỗ đỗ đã giữ", exact: true }),
  ).toContainText(slotId!);
});
