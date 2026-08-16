import type { CSSProperties, KeyboardEvent } from "react";

import type { MapNode, ParkingSlot as ParkingSlotData } from "@/lib/types";
import { getDisplayPoint } from "@/lib/map-geometry";

const STATUS_SIGNALS = {
  AVAILABLE: { icon: "✓", label: "Đang trống" },
  RESERVED: { icon: "R", label: "Đã giữ" },
  OCCUPIED: { icon: "●", label: "Đã có xe" },
} as const;

export interface ParkingSlotProps {
  slot: ParkingSlotData;
  displayNode: MapNode;
  recommended?: boolean;
  selected?: boolean;
  activeReservation?: boolean;
  parkedVehicle?: boolean;
  currentLocation?: boolean;
  onSelect?: (slotId: string) => void;
}

export function ParkingSlot({
  slot,
  displayNode,
  recommended = false,
  selected = false,
  activeReservation = false,
  parkedVehicle = false,
  currentLocation = false,
  onSelect,
}: ParkingSlotProps) {
  const signal = STATUS_SIGNALS[slot.status];
  const flags = [
    slot.has_charger ? "Có sạc điện" : null,
    slot.is_accessible ? "Dễ tiếp cận" : null,
    recommended ? "Được đề xuất" : null,
    selected ? "Đang được chọn" : null,
    activeReservation ? "Chỗ đã giữ" : null,
    parkedVehicle ? "Xe của bạn" : null,
    currentLocation ? "Vị trí hiện tại" : null,
  ].filter(Boolean);
  const className = [
    "map-slot",
    `status-${slot.status.toLowerCase()}`,
    slot.has_charger ? "is-ev" : "",
    slot.is_accessible ? "is-accessible" : "",
    recommended ? "is-recommended" : "",
    selected ? "is-selected" : "",
    activeReservation ? "is-reservation" : "",
    parkedVehicle ? "is-parked" : "",
    currentLocation ? "is-current-location" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const [displayX, displayY] = getDisplayPoint(displayNode);
  const style = {
    left: `${displayX}%`,
    top: `${displayY}%`,
  } as CSSProperties;

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect?.(slot.id);
    }
  }

  return (
    <button
      type="button"
      className={className}
      style={style}
      onClick={() => onSelect?.(slot.id)}
      onKeyDown={handleKeyDown}
      aria-pressed={selected}
      aria-label={`Ô đỗ ${slot.id}, Khu ${slot.zone_id}, ${signal.label}${flags.length ? `, ${flags.join(", ")}` : ""}`}
      data-slot-id={slot.id}
      data-status={slot.status}
      data-zone={slot.zone_id}
      data-x={displayX}
      data-y={displayY}
    >
      <span className="map-slot-signal" aria-hidden="true">
        {signal.icon}
      </span>
      <b>{slot.id.slice(3)}</b>
      <span className="map-slot-features" aria-hidden="true">
        {slot.has_charger ? "⚡" : ""}
        {slot.is_accessible ? "♿" : ""}
      </span>
      {recommended && <span className="map-slot-badge">Đề xuất</span>}
      {activeReservation && <span className="map-slot-badge reservation">Đã giữ</span>}
      {parkedVehicle && <span className="map-slot-badge parked">Xe của bạn</span>}
    </button>
  );
}
