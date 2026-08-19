import { describe, expect, it } from "vitest";

import { adjacentParkingSlotIds } from "./adjacent-parking-slots";

describe("adjacentParkingSlotIds", () => {
  it("returns only left and right slots in the same physical row", () => {
    expect(adjacentParkingSlotIds("F1-A01")).toEqual(["F1-A02"]);
    expect(adjacentParkingSlotIds("F1-A03")).toEqual(["F1-A02", "F1-A04"]);
    expect(adjacentParkingSlotIds("F1-A05")).toEqual(["F1-A04"]);
    expect(adjacentParkingSlotIds("F1-D06")).toEqual(["F1-D07"]);
    expect(adjacentParkingSlotIds("F1-D08")).toEqual(["F1-D07", "F1-D09"]);
    expect(adjacentParkingSlotIds("F1-D10")).toEqual(["F1-D09"]);
  });
});
