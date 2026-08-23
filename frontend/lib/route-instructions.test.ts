import { describe, expect, it } from "vitest";

import { canonicalMap } from "@/test/fixtures";

import { buildRouteInstructions } from "./route-instructions";

describe("buildRouteInstructions", () => {
  it("derives start, right turn, straight movement and arrival from route geometry", () => {
    const instructions = buildRouteInstructions(
      {
        path: ["F1-ENTRANCE", "F1-CP1", "F1-C-W", "F1-C01"],
        distance_m: 39,
        polyline: [[0, 50], [15, 50], [25, 70], [27, 74]],
      },
      canonicalMap,
    );

    expect(instructions.map((instruction) => instruction.kind)).toEqual([
      "START",
      "RIGHT",
      "STRAIGHT",
      "ARRIVE",
    ]);
    expect(instructions[1]).toMatchObject({ icon: "↱", label: "Rẽ phải" });
    expect(instructions[1].description).toBe("Ở ngã tư phía trước, rẽ phải.");
    expect(instructions.map((instruction) => instruction.description).join(" ")).not.toMatch(
      /checkpoint|điểm kiểm tra|F1-CP|F1-C-W/i,
    );
    expect(instructions.at(-1)?.description).toContain("Ô C01");
  });

  it("derives a left turn and falls back to map coordinates when polyline is absent", () => {
    const instructions = buildRouteInstructions(
      {
        path: ["F1-ENTRANCE", "F1-CP1", "F1-A-W", "F1-A01"],
        distance_m: 39,
        polyline: [],
      },
      canonicalMap,
    );

    expect(instructions[1].kind).toBe("LEFT");
    expect(instructions[1].icon).toBe("↰");
    expect(instructions[1].description).toBe("Ở ngã tư phía trước, rẽ trái.");
  });

  it("uses a safe continue instruction when geometry is unavailable", () => {
    const instructions = buildRouteInstructions(
      {
        path: ["F1-UNKNOWN-1", "F1-UNKNOWN-2", "F1-UNKNOWN-3"],
        distance_m: 10,
        polyline: [],
      },
      null,
    );

    expect(instructions[1]).toMatchObject({ kind: "CONTINUE", icon: "→" });
    expect(instructions[1].description).not.toMatch(/rẽ trái|rẽ phải/i);
  });
});
