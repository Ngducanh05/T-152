import type { FloorScopedId } from "./types";

const SLOT_ID = /^(F[1-3])-([A-D])(0[1-9]|10)$/;

export function adjacentParkingSlotIds(slotId: string): FloorScopedId[] {
  const match = SLOT_ID.exec(slotId);
  if (!match) return [];
  const floorId = match[1];
  const zoneId = match[2];
  const number = Number(match[3]);
  const rowStart = number <= 5 ? 1 : 6;
  const rowEnd = rowStart + 4;
  return [number - 1, number + 1]
    .filter((candidate) => candidate >= rowStart && candidate <= rowEnd)
    .map((candidate) => `${floorId}-${zoneId}${String(candidate).padStart(2, "0")}`);
}
