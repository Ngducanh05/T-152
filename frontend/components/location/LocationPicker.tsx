"use client";

import { useMemo, useRef, useState } from "react";

import { formatParkingLocation } from "@/lib/parking-display";
import type { FloorScopedId, MapNode, ParkingMap, ZoneId } from "@/lib/types";

const SPECIAL_TYPES = new Set<MapNode["type"]>([
  "ENTRANCE",
  "EXIT",
  "CHECKPOINT",
  "ELEVATOR",
]);
const SPECIAL_TYPE_ORDER: Record<string, number> = {
  ENTRANCE: 0,
  EXIT: 1,
  CHECKPOINT: 2,
  ELEVATOR: 3,
};
const ZONES: ZoneId[] = ["A", "B", "C", "D"];

interface LocationPickerProps {
  map: ParkingMap | null;
  currentLocationId: FloorScopedId | null;
  pending: boolean;
  errorMessage?: string | null;
  onClose: () => void;
  onConfirm: (nodeId: FloorScopedId) => Promise<boolean>;
}

export function LocationPicker({
  map,
  currentLocationId,
  pending,
  errorMessage,
  onClose,
  onConfirm,
}: LocationPickerProps) {
  const [showSlotChoices, setShowSlotChoices] = useState(false);
  const [selectedZone, setSelectedZone] = useState<ZoneId | null>(null);
  const [submittingTarget, setSubmittingTarget] =
    useState<FloorScopedId | null>(null);
  const submittingRef = useRef(false);

  const specialNodes = useMemo(
    () =>
      (map?.nodes ?? [])
        .filter((node) => SPECIAL_TYPES.has(node.type))
        .toSorted(
          (left, right) =>
            SPECIAL_TYPE_ORDER[left.type] - SPECIAL_TYPE_ORDER[right.type] ||
            left.id.localeCompare(right.id, undefined, { numeric: true }),
        ),
    [map],
  );
  const zoneSlots = useMemo(
    () =>
      (map?.slots ?? [])
        .filter((slot) => slot.zone_id === selectedZone)
        .toSorted((left, right) =>
          left.id.localeCompare(right.id, undefined, { numeric: true }),
        ),
    [map, selectedZone],
  );
  const busy = pending || submittingTarget !== null;

  async function submitLocation(nodeId: FloorScopedId) {
    if (busy || submittingRef.current) return;
    submittingRef.current = true;
    setSubmittingTarget(nodeId);
    try {
      const success = await onConfirm(nodeId);
      if (success) onClose();
    } finally {
      submittingRef.current = false;
      setSubmittingTarget(null);
    }
  }

  function requestClose() {
    if (!busy) onClose();
  }

  return (
    <div
      className="modal-backdrop"
      onClick={requestClose}
      onKeyDown={(event) => {
        if (event.key === "Escape") requestClose();
      }}
    >
      <section
        className="modal location-picker"
        role="dialog"
        aria-modal="true"
        aria-labelledby="location-picker-title"
        aria-describedby="location-picker-description"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          className="modal-close"
          onClick={requestClose}
          aria-label="Đóng chọn vị trí"
          disabled={busy}
        >
          ×
        </button>
        <p className="eyebrow green">VỊ TRÍ TRONG BÃI</p>
        <h2 id="location-picker-title">Xác nhận vị trí hiện tại</h2>
        <p id="location-picker-description">
          Chọn nơi bạn đang đứng. ParkSmart không dùng GPS và việc chọn vị trí
          không tự giữ ô hay xác nhận đã đỗ.
        </p>

        <div className="location-tap-list" role="group" aria-label="Địa điểm đặc biệt">
          {specialNodes.map((node) => (
            <button
              key={node.id}
              type="button"
              aria-pressed={currentLocationId === node.id}
              onClick={() => void submitLocation(node.id)}
              disabled={busy}
            >
              <span aria-hidden="true">⌖</span>
              <b>{formatParkingLocation(node.id)}</b>
            </button>
          ))}
        </div>

        <button
          type="button"
          className="slot-nearby-toggle"
          aria-expanded={showSlotChoices}
          onClick={() => setShowSlotChoices((current) => !current)}
          disabled={busy || !map}
        >
          <span aria-hidden="true">P</span>
          <b>Tôi đang cạnh một ô đỗ</b>
        </button>

        {showSlotChoices && (
          <div className="slot-tap-picker">
            <p>Bước 1 · Chọn khu</p>
            <div className="zone-tap-grid" role="group" aria-label="Chọn khu đỗ xe">
              {ZONES.map((zone) => (
                <button
                  key={zone}
                  type="button"
                  aria-pressed={selectedZone === zone}
                  onClick={() => setSelectedZone(zone)}
                  disabled={busy}
                >
                  Khu {zone}
                </button>
              ))}
            </div>
            {selectedZone && (
              <>
                <p>Bước 2 · Chọn số ô</p>
                <div className="slot-number-grid" role="group" aria-label={`Chọn ô khu ${selectedZone}`}>
                  {zoneSlots.map((slot) => (
                    <button
                      key={slot.id}
                      type="button"
                      aria-label={`Chọn ô ${slot.id.slice(-2)} khu ${selectedZone}`}
                      aria-pressed={currentLocationId === slot.id}
                      onClick={() => void submitLocation(slot.id)}
                      disabled={busy}
                    >
                      {slot.id.slice(-2)}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {errorMessage && <p className="location-api-error" role="alert">{errorMessage}</p>}
        {submittingTarget && (
          <p className="location-pending" role="status" aria-live="polite">
            Đang xác nhận {formatParkingLocation(submittingTarget)}…
          </p>
        )}
      </section>
    </div>
  );
}
