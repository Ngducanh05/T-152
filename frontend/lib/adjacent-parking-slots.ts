import type { FloorScopedId } from "./types";

const SLOT_ID = /^F1-([A-D])(0[1-9]|10)$/;

export function adjacentParkingSlotIds(slotId: string): FloorScopedId[] {
  const match = SLOT_ID.exec(slotId);
  if (!match) return [];
  const zoneId = match[1];
  const number = Number(match[2]);
  const rowStart = number <= 5 ? 1 : 6;
  const rowEnd = rowStart + 4;
  return [number - 1, number + 1]
    .filter((candidate) => candidate >= rowStart && candidate <= rowEnd)
    .map((candidate) => `F1-${zoneId}${String(candidate).padStart(2, "0")}`);
}
