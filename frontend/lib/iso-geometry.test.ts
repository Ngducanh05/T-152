import { describe, expect, it } from "vitest";

import {
  buildIsoBox,
  buildIsoRamp,
  buildIsoRhombus,
  buildIsoRibbon,
  buildIsoRibbonPath,
  isoDepth,
  pointsToPolygon,
  projectIso,
  projectIsoPath,
  toIsoPercent,
} from "./iso-geometry";

describe("iso-geometry", () => {
  // AC-5
  it("AC-5: projectIso([50, 50]) khớp tuyệt đối [100, 62]", () => {
    const [x, y] = projectIso([50, 50]);
    expect(x).toBe(100);
    expect(y).toBe(62);
  });

  // AC-6
  it("AC-6: projectIso([0, 0]) khớp tuyệt đối [100, 12]", () => {
    const [x, y] = projectIso([0, 0]);
    expect(x).toBe(100);
    expect(y).toBe(12);
  });

  // AC-7
  it("AC-7: projectIso([100, 100]) khớp tuyệt đối [100, 112]", () => {
    const [x, y] = projectIso([100, 100]);
    expect(x).toBe(100);
    expect(y).toBe(112);
  });

  // AC-8
  it("AC-8: projectIso([100, 0]) xấp xỉ [186.603, 62]", () => {
    const [x, y] = projectIso([100, 0]);
    expect(x).toBeCloseTo(186.603, 3);
    expect(y).toBeCloseTo(62, 3);
  });

  // AC-9
  it("AC-9: projectIso([0, 100]) xấp xỉ [13.397, 62]", () => {
    const [x, y] = projectIso([0, 100]);
    expect(x).toBeCloseTo(13.397, 3);
    expect(y).toBeCloseTo(62, 3);
  });

  // AC-10
  it("AC-10: projectIso([55, 61]) xấp xỉ [94.804, 70]", () => {
    const [x, y] = projectIso([55, 61]);
    expect(x).toBeCloseTo(94.804, 3);
    expect(y).toBeCloseTo(70, 3);
  });

  // AC-11
  it("AC-11: isoDepth([0,0]) < isoDepth([50,50]) < isoDepth([100,100])", () => {
    const d0 = isoDepth([0, 0]);
    const d50 = isoDepth([50, 50]);
    const d100 = isoDepth([100, 100]);
    expect(d0).toBeLessThan(d50);
    expect(d50).toBeLessThan(d100);
  });

  // AC-12
  it("AC-12: Mọi điểm chiếu của u,v trong [0,100] nằm trong x in [13.39, 186.61], y in [11.99, 112.01]", () => {
    for (let u = 0; u <= 100; u += 5) {
      for (let v = 0; v <= 100; v += 5) {
        const [x, y] = projectIso([u, v]);
        expect(x).toBeGreaterThanOrEqual(13.39);
        expect(x).toBeLessThanOrEqual(186.61);
        expect(y).toBeGreaterThanOrEqual(11.99);
        expect(y).toBeLessThanOrEqual(112.01);
      }
    }
  });

  // AC-18
  it("AC-18: buildIsoRibbon ném lỗi khi đoạn không song song trục", () => {
    expect(() => buildIsoRibbon([0, 0], [10, 10], 5)).toThrow();
    expect(() => buildIsoRibbon([20, 10], [30, 25], 4)).toThrow();
  });

  it("buildIsoRhombus trả về 4 điểm theo đúng thứ tự sau-phải-trước-trái", () => {
    const center: [number, number] = [50, 50];
    const rhombus = buildIsoRhombus(center, 10, 10);
    expect(rhombus).toHaveLength(4);

    const [p0, p1, p2, p3] = rhombus;
    // p0 = [40, 40] -> sau (u+v bé nhất)
    // p1 = [60, 40] -> phải
    // p2 = [60, 60] -> trước (u+v lớn nhất)
    // p3 = [40, 60] -> trái
    expect(p0).toEqual(projectIso([40, 40]));
    expect(p1).toEqual(projectIso([60, 40]));
    expect(p2).toEqual(projectIso([60, 60]));
    expect(p3).toEqual(projectIso([40, 60]));
    expect(p0[1]).toBeLessThan(p2[1]);
    expect(p3[0]).toBeLessThan(p1[0]);
  });

  it("buildIsoBox trả về đúng 3 mặt mỗi mặt 4 điểm cho cả height > 0 và height < 0", () => {
    const boxUp = buildIsoBox([50, 50], 5, 5, 10);
    expect(boxUp.top).toHaveLength(4);
    expect(boxUp.left).toHaveLength(4);
    expect(boxUp.right).toHaveLength(4);

    const boxDown = buildIsoBox([50, 50], 50, 50, -7);
    expect(boxDown.top).toHaveLength(4);
    expect(boxDown.left).toHaveLength(4);
    expect(boxDown.right).toHaveLength(4);
  });

  it("buildIsoRamp tạo vạch dọc và miệng hầm riêng cho lối xuống", () => {
    const rampUp = buildIsoRamp([85, 75], 5, 6, 8);
    expect(rampUp.deck).toHaveLength(4);
    expect(rampUp.left).toHaveLength(3);
    expect(rampUp.right).toHaveLength(3);
    expect(rampUp.direction).toBe("UP");
    expect(rampUp.opening).toBeNull();
    expect(rampUp.centerLine[0]).toEqual([
      (rampUp.deck[3][0] + rampUp.deck[2][0]) / 2,
      (rampUp.deck[3][1] + rampUp.deck[2][1]) / 2,
    ]);
    expect(rampUp.centerLine[1]).toEqual([
      (rampUp.deck[0][0] + rampUp.deck[1][0]) / 2,
      (rampUp.deck[0][1] + rampUp.deck[1][1]) / 2,
    ]);

    const rampDown = buildIsoRamp([85, 75], 5, 6, -8);
    expect(rampDown.direction).toBe("DOWN");
    expect(rampDown.opening).toHaveLength(4);
    expect(rampDown.sideLines[0]).toEqual([rampDown.deck[3], rampDown.deck[0]]);
    expect(rampDown.sideLines[1]).toEqual([rampDown.deck[2], rampDown.deck[1]]);
  });

  it("toIsoPercent([100, 62]) trả về [50, 44.286...]", () => {
    const [px, py] = toIsoPercent([100, 62]);
    expect(px).toBe(50);
    expect(py).toBeCloseTo(44.286, 3);
  });

  it("projectIsoPath và pointsToPolygon chuyển đổi chính xác", () => {
    const path = projectIsoPath([
      [0, 0],
      [50, 50],
      [100, 100],
    ]);
    expect(path).toEqual([
      [100, 12],
      [100, 62],
      [100, 112],
    ]);
    const polyStr = pointsToPolygon(path);
    expect(polyStr).toBe("100,12 100,62 100,112");
  });

  it("buildIsoRibbon và buildIsoRibbonPath mở rộng các đoạn thẳng song song trục", () => {
    const ribbonH = buildIsoRibbon([0, 50], [100, 50], 6);
    expect(ribbonH).toHaveLength(4);

    const ribbonV = buildIsoRibbon([50, 7], [50, 50], 6);
    expect(ribbonV).toHaveLength(4);

    const pathQuads = buildIsoRibbonPath(
      [
        [20, 50],
        [20, 7],
        [80, 7],
        [80, 50],
      ],
      6,
    );
    expect(pathQuads).toHaveLength(3);
  });
});
