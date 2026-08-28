"use client";

import { formatParkingLocation } from "@/lib/parking-display";
import type { FloorScopedId, ParkingReservation } from "@/lib/types";

interface LocationConfirmationOutcomeProps {
  locationId: FloorScopedId;
  activeReservation: ParkingReservation | null;
  pending: boolean;
  onConfirmParking: () => Promise<unknown> | unknown;
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
        Đã cập nhật vị trí hiện tại thành {formatParkingLocation(locationId)}.
      </div>
    );
  }

  if (activeReservation.slot_id !== locationId) {
    return (
      <div className="location-confirmation-outcome mismatch" role="alert">
        Bạn đang giữ {formatParkingLocation(activeReservation.slot_id)} nhưng vị trí vừa
        xác nhận là {formatParkingLocation(locationId)}. Xe vẫn chưa được ghi nhận là đã đỗ.
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
        <b>Bạn đã xác nhận đang ở {formatParkingLocation(locationId)}.</b>
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
