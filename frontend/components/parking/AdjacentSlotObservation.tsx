"use client";

import { adjacentParkingSlotIds } from "@/lib/adjacent-parking-slots";
import { formatParkingLocation, formatSlotStatus } from "@/lib/parking-display";
import type {
  AdjacentSlotObservedStatus,
  ParkingSlot,
} from "@/lib/types";

interface AdjacentSlotObservationProps {
  parkedSlotId: string;
  slots: ParkingSlot[];
  pendingSlotId: string | null;
  onObserve: (
    slotId: string,
    status: AdjacentSlotObservedStatus,
  ) => Promise<void>;
}

export function AdjacentSlotObservation({
  parkedSlotId,
  slots,
  pendingSlotId,
  onObserve,
}: AdjacentSlotObservationProps) {
  const adjacentSlots = adjacentParkingSlotIds(parkedSlotId)
    .map((slotId) => slots.find((slot) => slot.id === slotId))
    .filter((slot): slot is ParkingSlot => slot !== undefined);
  if (adjacentSlots.length === 0) return null;

  return (
    <section
      className="adjacent-slot-observation"
      aria-labelledby="adjacent-observation-title"
    >
      <header>
        <div>
          <b id="adjacent-observation-title">Hai ô bên cạnh thế nào?</b>
          <small>Không bắt buộc · thông tin được gửi về ParkSmart</small>
        </div>
      </header>
      <div className="adjacent-observation-grid">
        {adjacentSlots.map((slot) => {
          const pending = pendingSlotId === slot.id;
          const observationDisabled = pendingSlotId !== null || slot.status === "RESERVED";
          return (
            <article key={slot.id}>
              <div>
                <strong>{formatParkingLocation(slot.id)}</strong>
                <small>Hiện tại: {formatSlotStatus(slot.status)}</small>
              </div>
              {slot.status === "RESERVED" ? (
                <p>Ô đang được giữ, không thể ghi đè.</p>
              ) : (
                <div>
                  <button
                    type="button"
                    disabled={observationDisabled}
                    aria-label={`Báo ${slot.id} đang trống`}
                    onClick={() => void onObserve(slot.id, "AVAILABLE")}
                  >
                    <span aria-hidden="true">✓</span> Trống
                  </button>
                  <button
                    type="button"
                    disabled={observationDisabled}
                    aria-label={`Báo ${slot.id} có xe đỗ`}
                    onClick={() => void onObserve(slot.id, "OCCUPIED")}
                  >
                    <span aria-hidden="true">●</span> Có xe
                  </button>
                </div>
              )}
              {pending && <p role="status">Đang cập nhật…</p>}
            </article>
          );
        })}
      </div>
    </section>
  );
}
