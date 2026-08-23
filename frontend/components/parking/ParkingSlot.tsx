import type { CSSProperties, KeyboardEvent } from "react";

import type { MapNode, ParkingSlot as ParkingSlotData } from "@/lib/types";
import { getDisplayPoint, type MapPoint } from "@/lib/map-geometry";

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
  openReportCount?: number;
  pendingObservationCount?: number;
  onSelect?: (slotId: string) => void;
  onOpenReportedSlot?: (slotId: string) => void;
  onOpenObservedSlot?: (slotId: string) => void;

  /** Vị trí % đã tính sẵn. Bỏ trống thì dùng getDisplayPoint(displayNode) như cũ. */
  position?: MapPoint;

  /** "flat" (mặc định) giữ nguyên; "iso" thêm class .map-slot--iso. */
  variant?: "flat" | "iso";

  /** z-index nội tuyến, chỉ dùng khi variant="iso". */
  depthIndex?: number;
}

export function ParkingSlot({
  slot,
  displayNode,
  recommended = false,
  selected = false,
  activeReservation = false,
  parkedVehicle = false,
  currentLocation = false,
  openReportCount = 0,
  pendingObservationCount = 0,
  onSelect,
  onOpenReportedSlot,
  onOpenObservedSlot,
  position,
  variant = "flat",
  depthIndex,
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
    openReportCount > 0 ? `${openReportCount} báo cáo đang mở` : null,
    pendingObservationCount > 0
      ? `${pendingObservationCount} quan sát chờ xác minh`
      : null,
  ].filter(Boolean);
  const className = [
    "map-slot",
    variant === "iso" ? "map-slot--iso" : "",
    `status-${slot.status.toLowerCase()}`,
    slot.has_charger ? "is-ev" : "",
    slot.is_accessible ? "is-accessible" : "",
    recommended ? "is-recommended" : "",
    selected ? "is-selected" : "",
    activeReservation ? "is-reservation" : "",
    parkedVehicle ? "is-parked" : "",
    currentLocation ? "is-current-location" : "",
    openReportCount > 0 ? "has-open-reports" : "",
    pendingObservationCount > 0 ? "has-pending-observations" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const [displayX, displayY] = position ?? getDisplayPoint(displayNode);
  const style = {
    left: `${displayX}%`,
    top: `${displayY}%`,
    ...(depthIndex !== undefined ? { zIndex: depthIndex } : {}),
  } as CSSProperties;

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      activateSlot();
    }
  }

  function activateSlot() {
    onSelect?.(slot.id);
    if (openReportCount > 0) {
      onOpenReportedSlot?.(slot.id);
      return;
    }
    if (pendingObservationCount > 0) {
      onOpenObservedSlot?.(slot.id);
      return;
    }
  }

  if (variant === "iso") {
    return (
      <div
        className="map-slot-wrapper map-slot-wrapper--iso"
        style={style}
        data-slot-id={slot.id}
      >
        <button
          type="button"
          className={className}
          onClick={activateSlot}
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
        </button>
        <div className="map-slot-badges--iso" aria-hidden="true">
          {currentLocation && (
            <span className="map-slot-current-marker" aria-hidden="true">
              ⌖
            </span>
          )}
          {recommended && <span className="map-slot-badge">Đề xuất</span>}
          {activeReservation && (
            <span className="map-slot-badge reservation">Đã giữ</span>
          )}
          {parkedVehicle && (
            <span className="map-slot-badge parked">Xe của bạn</span>
          )}
          {openReportCount > 0 && (
            <span className="map-slot-report-warning">
              <span>!</span>
              <b>{openReportCount}</b>
            </span>
          )}
          {pendingObservationCount > 0 && (
            <span className="map-slot-observation-warning">
              <span>?</span>
              <b>{pendingObservationCount}</b>
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      className={className}
      style={style}
      onClick={activateSlot}
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
      {openReportCount > 0 && (
        <span className="map-slot-report-warning" aria-hidden="true">
          <span>!</span>
          <b>{openReportCount}</b>
        </span>
      )}
      {pendingObservationCount > 0 && (
        <span className="map-slot-observation-warning" aria-hidden="true">
          <span>?</span>
          <b>{pendingObservationCount}</b>
        </span>
      )}
    </button>
  );
}
