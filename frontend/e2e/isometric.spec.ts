import { expect, test } from "@playwright/test";
import { apiUrl, slotButton } from "./helpers";

test.describe("Isometric View (Phase 12)", () => {
  test.beforeEach(async ({ page }) => {
    const reset = await page.request.post(`${apiUrl}/simulator/reset`, { data: {} });
    expect(reset.status()).toBe(200);
  });

  test("AC-27: hover ô A01 không làm đổi boundingBox (không bị dịch transform)", async ({ page }) => {
    await page.goto("/admin");
    await expect(page.getByTestId("parking-map")).toBeVisible();

    // Bật phối cảnh hầm
    await page.getByRole("button", { name: "Phối cảnh hầm" }).click();
    await expect(page.getByTestId("isometric-map")).toBeVisible();

    const a01 = slotButton(page, "F1-A01");
    await expect(a01).toBeVisible();
    await a01.scrollIntoViewIfNeeded();

    const boxBefore = await a01.boundingBox();
    expect(boxBefore).not.toBeNull();

    // Di chuyển chuột đến tâm ô A01
    const centerX = boxBefore!.x + boxBefore!.width / 2;
    const centerY = boxBefore!.y + boxBefore!.height / 2;
    await page.mouse.move(centerX, centerY);
    await page.waitForTimeout(100);

    const boxAfter = await a01.boundingBox();
    expect(boxAfter).not.toBeNull();

    expect(Math.abs(boxAfter!.x - boxBefore!.x)).toBeLessThan(1);
    expect(Math.abs(boxAfter!.y - boxBefore!.y)).toBeLessThan(1);
    expect(Math.abs(boxAfter!.width - boxBefore!.width)).toBeLessThan(1);
    expect(Math.abs(boxAfter!.height - boxBefore!.height)).toBeLessThan(1);
  });

  test("AC-28: Tab tới ô A01 không làm đổi boundingBox khi nhận focus", async ({ page }) => {
    await page.goto("/admin");
    await expect(page.getByTestId("parking-map")).toBeVisible();

    await page.getByRole("button", { name: "Phối cảnh hầm" }).click();
    await expect(page.getByTestId("isometric-map")).toBeVisible();

    const a01 = slotButton(page, "F1-A01");
    await expect(a01).toBeVisible();
    await a01.scrollIntoViewIfNeeded();

    const boxBefore = await a01.boundingBox();
    expect(boxBefore).not.toBeNull();

    // Mô phỏng bàn phím thật: Tab liên tục tới khi A01 nhận focus
    for (let i = 0; i < 50; i++) {
      const isFocused = await a01.evaluate((el) => el === document.activeElement);
      if (isFocused) break;
      await page.keyboard.press("Tab");
    }
    await expect(a01).toBeFocused();

    const boxAfter = await a01.boundingBox();
    expect(boxAfter).not.toBeNull();

    expect(Math.abs(boxAfter!.x - boxBefore!.x)).toBeLessThan(1);
    expect(Math.abs(boxAfter!.y - boxBefore!.y)).toBeLessThan(1);
    expect(Math.abs(boxAfter!.width - boxBefore!.width)).toBeLessThan(1);
    expect(Math.abs(boxAfter!.height - boxBefore!.height)).toBeLessThan(1);
  });

  test("AC-29: click vào tâm ô A02 kích hoạt đúng F1-A02 (không bị ô khác đè)", async ({ page }) => {
    // Tạo 1 báo cáo đỗ sai trên ô F1-A02 qua API backend
    const reportRes = await page.request.post(`${apiUrl}/reports/wrong-parking`, {
      data: {
        user_id: "USER-001",
        slot_id: "F1-A02",
        reason_code: "CROSSED_LINE",
      },
    });
    expect(reportRes.status()).toBe(201);

    await page.goto("/admin");
    await expect(page.getByTestId("parking-map")).toBeVisible();

    await page.getByRole("button", { name: "Phối cảnh hầm" }).click();
    await expect(page.getByTestId("isometric-map")).toBeVisible();

    // Focus ô A01 trước
    const a01 = slotButton(page, "F1-A01");
    await a01.scrollIntoViewIfNeeded();
    await a01.focus();
    await expect(a01).toBeFocused();

    // Di chuyển chuột đến tâm ô A02 và click thật
    const a02 = slotButton(page, "F1-A02");
    await expect(a02).toBeVisible();
    const boxA02 = await a02.boundingBox();
    expect(boxA02).not.toBeNull();

    const centerX = boxA02!.x + boxA02!.width / 2;
    const centerY = boxA02!.y + boxA02!.height / 2;
    await page.mouse.move(centerX, centerY);
    await page.mouse.down();
    await page.mouse.up();

    // Chứng minh click handler của A02 chạy: drawer báo cáo mở ra cho ô A02
    const drawer = page.getByRole("dialog", { name: /Ô A02/ });
    await expect(drawer).toBeVisible();
    await expect(drawer).toContainText("Ô A02");
    await expect(drawer).not.toContainText("F1-A01");
  });

  test("AC-30: Ô đang là vị trí hiện tại: marker ⌖ hiển thị đầy đủ và không bị clip-path xén", async ({ page }) => {
    await page.goto("/test-isometric");
    await expect(page.getByTestId("parking-map")).toBeVisible();

    // Chuyển sang Phối cảnh hầm
    await page.getByRole("button", { name: "Phối cảnh hầm" }).click();
    await expect(page.getByTestId("isometric-map")).toBeVisible();

    // 1. Locate marker thật trên ô F1-A01 (được truyền currentLocation=true)
    const marker = page.locator("[data-slot-id='F1-A01'] .map-slot-current-marker");
    await expect(marker).toBeVisible();
    await expect(marker).toHaveText("⌖");

    // 2. Đo bounding box của chính marker ⌖
    const box = await marker.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThan(5);
    expect(box!.height).toBeGreaterThan(5);

    // 3. Xác nhận quan hệ sibling: marker nằm trong .map-slot-badges--iso, KHÔNG nằm dưới button .map-slot--iso bị clip
    const isMarkerInsideButton = await page
      .locator(".map-slot-wrapper--iso[data-slot-id='F1-A01']")
      .first()
      .evaluate((el) => {
        const button = el.querySelector(".map-slot--iso");
        const markerEl = el.querySelector(".map-slot-current-marker");
        return button && markerEl ? button.contains(markerEl) : false;
      });
    expect(isMarkerInsideButton).toBe(false);

    // 4. Xác nhận parent container .map-slot-badges--iso có overflow: visible và clipPath: none
    const badgesComputed = await page
      .locator(".map-slot-wrapper--iso[data-slot-id='F1-A01'] .map-slot-badges--iso")
      .evaluate((el) => {
        const s = window.getComputedStyle(el);
        return {
          overflow: s.overflow,
          clipPath: s.clipPath,
          position: s.position,
        };
      });
    expect(badgesComputed.overflow).toBe("visible");
    expect(badgesComputed.clipPath).toBe("none");
    expect(badgesComputed.position).toBe("absolute");
  });

  test("AC-31: Route F1→F2 có ít nhất 2 node ở mỗi tầng; chuyển sang tab Tầng 2, trên F2 không vẽ bất kỳ đoạn nào thuộc F1 ở cả 2D và iso", async ({ page }) => {
    await page.goto("/test-isometric");
    await expect(page.getByTestId("parking-map")).toBeVisible();

    // 1. Ở F1 phẳng (2D): đường route .map-route-line vẽ đúng đoạn F1
    const flatF1Route = page.locator(".map-network:not(.map-network--iso) .map-route-line");
    await expect(flatF1Route).toBeVisible();
    const flatF1Points = await flatF1Route.getAttribute("points");
    expect(flatF1Points).toBe("0,50 15,50 50,50 55,50 55,61");

    // 2. Chuyển sang Phối cảnh hầm ở F1 (iso): đường route .map-route-line vẽ theo toạ độ iso của F1
    await page.getByRole("button", { name: "Phối cảnh hầm" }).click();
    const isoF1Route = page.locator(".map-network--iso .map-route-line");
    await expect(isoF1Route).toBeVisible();
    const isoF1Points = await isoF1Route.getAttribute("points");
    expect(isoF1Points).toBe(
      "56.69872981077806,37 69.68911086754464,44.5 100,62 104.3301270189222,64.5 94.80384757729337,70",
    );

    // 3. Chuyển sang Tầng 2 (vẫn ở chế độ iso): route cắt đúng đoạn F2, assert toàn bộ chuỗi toạ độ iso F2
    await page.getByRole("button", { name: /Tầng 2:/ }).click();
    const isoF2Route = page.locator(".map-network--iso .map-route-line");
    await expect(isoF2Route).toBeVisible();
    const isoF2Points = await isoF2Route.getAttribute("points");
    expect(isoF2Points).toBe(
      "108.66025403784438,92 130.31088913245534,79.5 100,62 104.3301270189222,64.5 94.80384757729337,70",
    );
    expect(isoF2Points).not.toContain("56.69872981077806,37");
    expect(isoF2Points).not.toContain("69.68911086754464,44.5");

    // 4. Chuyển sang Sơ đồ phẳng ở Tầng 2 (2D): route cắt đúng đoạn F2 (85,75 -> 85,50 -> 50,50 -> 55,50 -> 55,61), không chứa toạ độ F1 (0,50 / 15,50)
    await page.getByRole("button", { name: "Sơ đồ phẳng" }).click();
    const flatF2Route = page.locator(".map-network:not(.map-network--iso) .map-route-line");
    await expect(flatF2Route).toBeVisible();
    const flatF2Points = await flatF2Route.getAttribute("points");
    expect(flatF2Points).toBe("85,75 85,50 50,50 55,50 55,61");
    const flatF2List = flatF2Points!.split(/\s+/);
    expect(flatF2List).not.toContain("0,50");
    expect(flatF2List).not.toContain("15,50");
    // 5. Xác nhận khoảng cách đã được tính lại cho riêng đoạn F2 (51m thay vì 150m của toàn tuyến)
    const routeContainer = page.locator(".map-network:not(.map-network--iso) .map-route");
    await expect(routeContainer).toHaveAttribute("aria-label", /dài 51 mét/);
    await expect(routeContainer).not.toHaveAttribute("aria-label", /150 mét/);
  });
});
