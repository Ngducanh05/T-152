"use client";

import type { FloorScopedId, ParkingReservation } from "@/lib/types";

interface LocationConfirmationOutcomeProps {
  locationId: FloorScopedId;
  activeReservation: ParkingReservation | null;
  pending: boolean;
  onConfirmParking: () => Promise<void> | void;
}

export function LocationConfirmationOutcome({
  locationId,
  activeReservation,
  pending,
  onConfirmParking,
}: LocationConfirmationOutcomeProps) {
  if (!activeReservation) {
    return (
      <div
        className="location-confirmation-outcome"
        role="status"
        aria-label="Kết quả xác nhận vị trí"
      >
        Đã cập nhật vị trí hiện tại thành {locationId}.
      </div>
    );
  }

  if (activeReservation.slot_id !== locationId) {
    return (
      <div className="location-confirmation-outcome mismatch" role="alert">
        Bạn đang có reservation tại {activeReservation.slot_id} nhưng vị trí vừa
        xác nhận là {locationId}. Hệ thống chưa xác nhận đỗ xe.
      </div>
    );
  }

  return (
    <div
      className="location-confirmation-outcome matching"
      role="status"
      aria-label="Kết quả xác nhận vị trí"
    >
      <div>
        <b>Bạn đã xác nhận đang ở {locationId}.</b>
        <span>Nếu xe đã đỗ đúng ô này, hãy xác nhận bước tiếp theo.</span>
      </div>
      <button
        type="button"
        onClick={() => void onConfirmParking()}
        disabled={pending}
      >
        {pending ? "Đang xác nhận…" : "Xác nhận đã đỗ"}
      </button>
    </div>
  );
}
