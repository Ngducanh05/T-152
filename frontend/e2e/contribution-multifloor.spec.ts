import { expect, test } from "@playwright/test";

import { apiUrl, slotButton } from "./helpers";

test.describe.configure({ mode: "serial" });

for (const scenario of [
  { floor: "F2", ownSlot: "F2-D03", observedSlot: "F2-D02" },
  { floor: "F3", ownSlot: "F3-A05", observedSlot: "F3-A04" },
]) {
  test(`${scenario.floor} contribution selects and highlights the correct isometric floor`, async ({
    page,
  }) => {
    expect(
      (await page.request.post(`${apiUrl}/simulator/reset`, { data: {} })).status(),
    ).toBe(200);

    const ownSlot = await page.request.get(
      `${apiUrl}/parking/slots/${scenario.ownSlot}`,
    );
    const reservation = await page.request.post(`${apiUrl}/reservations`, {
      data: {
        user_id: "USER-001",
        vehicle_id: "VEHICLE-001",
        slot_id: scenario.ownSlot,
        expected_version: (await ownSlot.json()).data.version,
      },
    });
    expect(reservation.status()).toBe(201);

    const reservedSlot = await page.request.get(
      `${apiUrl}/parking/slots/${scenario.ownSlot}`,
    );
    const parked = await page.request.post(`${apiUrl}/sessions/confirm-parking`, {
      data: {
        user_id: "USER-001",
        vehicle_id: "VEHICLE-001",
        reservation_id: (await reservation.json()).data.id,
        expected_version: (await reservedSlot.json()).data.version,
      },
    });
    expect(parked.status()).toBe(200);

    const target = await page.request.get(
      `${apiUrl}/parking/slots/${scenario.observedSlot}`,
    );
    const observation = await page.request.post(
      `${apiUrl}/parking/slots/${scenario.observedSlot}/observation`,
      {
        data: {
          user_id: "USER-001",
          observed_status: "OCCUPIED",
          expected_slot_version: (await target.json()).data.version,
        },
      },
    );
    expect(observation.status()).toBe(200);
    const observationId = (await observation.json()).data.id as string;

    await page.goto("/admin");
    const contribution = page.locator(
      `.observation-row[data-observation-id="${observationId}"]`,
    );
    await expect(contribution).toBeVisible();
    await contribution.click();
    await expect(
      page.getByRole("button", {
        name: new RegExp(`^Tầng ${scenario.floor.slice(1)}:`),
      }),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(
      page.locator(`.map-slot[data-slot-id^="${scenario.floor}-"]`),
    ).toHaveCount(40);

    await page.getByRole("button", { name: "Phối cảnh hầm" }).click();
    await expect(
      page.locator(`.map-slot--iso[data-slot-id^="${scenario.floor}-"]`),
    ).toHaveCount(40);
    const selectedSlot = slotButton(page, scenario.observedSlot);
    await expect(selectedSlot).toHaveClass(/is-selected/);
    await expect(selectedSlot).toHaveClass(/has-pending-observations/);

    await page.getByRole("button", { name: "Xác minh", exact: true }).click();
    await expect(contribution).toHaveCount(0);
    const verifiedSlot = await page.request.get(
      `${apiUrl}/parking/slots/${scenario.observedSlot}`,
    );
    expect((await verifiedSlot.json()).data.status).toBe("OCCUPIED");
  });
}
