"use client";

import type { Ref } from "react";

interface ParkSmartPointsButtonProps {
  availablePoints: number;
  onClick: () => void;
  buttonRef?: Ref<HTMLButtonElement>;
}

function formatBadge(points: number) {
  return points > 999 ? "999+" : String(Math.max(0, points));
}

export function ParkSmartPointsButton({
  availablePoints,
  onClick,
  buttonRef,
}: ParkSmartPointsButtonProps) {
  return (
    <button
      ref={buttonRef}
      type="button"
      className="parksmart-points-button"
      onClick={onClick}
      aria-label={`Open ParkSmart Points, ${Math.max(0, availablePoints)} available points`}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="m12 2 8 10-8 10L4 12 12 2Zm0 4.2L8 12l4 5.8 4-5.8-4-5.8Z" />
      </svg>
      <span className="parksmart-points-badge">{formatBadge(availablePoints)}</span>
      <span className="visually-hidden">ParkSmart Points</span>
    </button>
  );
}

export { formatBadge as formatPointsBadge };
