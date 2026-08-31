"use client";

interface ParkSmartPointsButtonProps {
  points: number;
  onOpen: () => void;
}

export function ParkSmartPointsButton({
  points,
  onOpen,
}: ParkSmartPointsButtonProps) {
  const badge = points > 999 ? "999+" : String(points);

  return (
    <button
      type="button"
      className="points-trigger"
      aria-label={`ParkSmart Points: ${points} điểm`}
      onClick={onOpen}
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        width="20"
        height="20"
        fill="none"
      >
        <path
          d="M12 2.75 14.7 8.2l6.02.88-4.36 4.24 1.03 5.99L12 16.48l-5.39 2.83 1.03-5.99-4.36-4.24 6.02-.88L12 2.75Z"
          fill="currentColor"
          stroke="currentColor"
          strokeLinejoin="round"
        />
        <circle cx="12" cy="12" r="2.1" fill="white" />
      </svg>
      <span className="points-badge">{badge}</span>
    </button>
  );
}
