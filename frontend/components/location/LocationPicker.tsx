"use client";

import {
  FormEvent,
  KeyboardEvent,
  useMemo,
  useRef,
  useState,
} from "react";

import type { FloorScopedId, MapNode, ParkingMap } from "@/lib/types";

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

interface LocationPickerProps {
  map: ParkingMap | null;
  currentLocationId: FloorScopedId | null;
  pending: boolean;
  errorMessage?: string | null;
  onClose: () => void;
  onConfirm: (nodeId: FloorScopedId) => Promise<boolean>;
}

function normalizedId(value: string): FloorScopedId {
  return value.trim().toUpperCase();
}

export function LocationPicker({
  map,
  currentLocationId,
  pending,
  errorMessage,
  onClose,
  onConfirm,
}: LocationPickerProps) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);
  const [validationMessage, setValidationMessage] = useState<string | null>(null);
  const [submittingTarget, setSubmittingTarget] = useState<FloorScopedId | null>(null);
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
  const slotNodes = useMemo(
    () =>
      (map?.nodes ?? [])
        .filter((node) => node.type === "SLOT")
        .toSorted((left, right) =>
          left.id.localeCompare(right.id, undefined, { numeric: true }),
        ),
    [map],
  );
  const normalizedQuery = normalizedId(query);
  const filteredSlots = useMemo(
    () =>
      normalizedQuery
        ? slotNodes.filter((node) => node.id.includes(normalizedQuery))
        : slotNodes,
    [normalizedQuery, slotNodes],
  );
  const busy = pending || submittingTarget !== null;

  async function submitLocation(nodeId: string) {
    const normalizedNodeId = normalizedId(nodeId);
    if (!normalizedNodeId || busy || submittingRef.current) return;

    submittingRef.current = true;
    setSubmittingTarget(normalizedNodeId);
    setValidationMessage(null);
    try {
      const success = await onConfirm(normalizedNodeId);
      if (success) onClose();
    } finally {
      submittingRef.current = false;
      setSubmittingTarget(null);
    }
  }

  function submitSlot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedNodeId = normalizedId(query);
    const exists = slotNodes.some((node) => node.id === normalizedNodeId);
    if (!exists) {
      setValidationMessage(
        "Không tìm thấy ID ô đỗ trong bản đồ hiện tại. Hãy chọn một ô trong danh sách.",
      );
      return;
    }
    void submitLocation(normalizedNodeId);
  }

  function chooseSlot(nodeId: FloorScopedId) {
    setQuery(nodeId);
    setActiveIndex(-1);
    setValidationMessage(null);
  }

  function handleComboboxKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) =>
        filteredSlots.length === 0 ? -1 : Math.min(current + 1, filteredSlots.length - 1),
      );
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) =>
        filteredSlots.length === 0
          ? -1
          : current <= 0
            ? filteredSlots.length - 1
            : current - 1,
      );
      return;
    }
    if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      chooseSlot(filteredSlots[activeIndex].id);
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
      <div
        className="modal location-picker"
        role="dialog"
        aria-modal="true"
        aria-labelledby="location-picker-title"
        aria-describedby="location-picker-description"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          className="modal-close"
          onClick={requestClose}
          aria-label="Đóng chọn vị trí"
          disabled={busy}
        >
          ×
        </button>
        <p className="eyebrow green">POST /LOCATIONS/CONFIRM</p>
        <h2 id="location-picker-title">Xác nhận vị trí hiện tại</h2>
        <p id="location-picker-description">
          Chọn một địa điểm nhanh hoặc tìm một trong 40 ô đỗ từ bản đồ. Việc xác
          nhận vị trí không giữ chỗ và không xác nhận đã đỗ xe.
        </p>

        <section className="location-picker-section" aria-labelledby="quick-location-title">
          <h3 id="quick-location-title">Địa điểm nhanh</h3>
          <div className="location-choice-grid" role="group" aria-label="Vị trí nhanh">
            {specialNodes.map((node) => (
              <button
                key={node.id}
                type="button"
                aria-pressed={currentLocationId === node.id}
                onClick={() => void submitLocation(node.id)}
                disabled={busy}
              >
                {node.id}
              </button>
            ))}
          </div>
        </section>

        <form className="slot-location-form" onSubmit={submitSlot}>
          <label htmlFor="slot-location-search">Tìm ô đỗ theo ID</label>
          <div className="slot-location-controls">
            <input
              id="slot-location-search"
              role="combobox"
              aria-autocomplete="list"
              aria-expanded="true"
              aria-controls="slot-location-options"
              aria-activedescendant={
                activeIndex >= 0 ? `slot-location-option-${filteredSlots[activeIndex].id}` : undefined
              }
              value={query}
              placeholder="Ví dụ: F1-D01"
              autoComplete="off"
              disabled={busy}
              onChange={(event) => {
                setQuery(event.target.value);
                setActiveIndex(-1);
                setValidationMessage(null);
              }}
              onKeyDown={handleComboboxKeyDown}
            />
            <button type="submit" disabled={busy || slotNodes.length === 0}>
              Xác nhận vị trí ô đỗ
            </button>
          </div>
          <div
            id="slot-location-options"
            className="slot-location-options"
            role="listbox"
            aria-label="Các ô đỗ khớp tìm kiếm"
          >
            {filteredSlots.map((node, index) => (
              <button
                id={`slot-location-option-${node.id}`}
                key={node.id}
                type="button"
                role="option"
                aria-selected={normalizedQuery === node.id}
                className={activeIndex === index ? "active" : ""}
                tabIndex={-1}
                onClick={() => chooseSlot(node.id)}
                disabled={busy}
              >
                {node.id}
              </button>
            ))}
            {filteredSlots.length === 0 && (
              <p role="status">Không có ô đỗ nào khớp tìm kiếm.</p>
            )}
          </div>
          {validationMessage && <p className="location-validation" role="alert">{validationMessage}</p>}
          {errorMessage && <p className="location-api-error" role="alert">{errorMessage}</p>}
        </form>

        {submittingTarget && (
          <p className="location-pending" role="status" aria-live="polite">
            Đang xác nhận {submittingTarget}…
          </p>
        )}
      </div>
    </div>
  );
}
