"use client";

import { useRef, useState } from "react";

import { adjacentParkingSlotIds } from "@/lib/adjacent-parking-slots";
import type {
  AdjacentSlotObservedStatus,
  ParkingSlot,
  SlotObservation,
} from "@/lib/types";

interface AdjacentSlotObservationProps {
  parkingSessionId: string;
  parkedSlotId: string;
  slots: ParkingSlot[];
  observedSlotIds: string[];
  rewardPoints: number;
  pendingSlotId: string | null;
  onObserve: (
    slotId: string,
    status: AdjacentSlotObservedStatus,
  ) => Promise<SlotObservation | null>;
}

function shortSlotName(slotId: string) {
  return slotId.split("-").at(-1) ?? slotId;
}

function slotPosition(slotId: string, parkedSlotId: string) {
  const target = Number(slotId.slice(-2));
  const parked = Number(parkedSlotId.slice(-2));
  return target < parked ? "bên trái" : "bên phải";
}

export function AdjacentSlotObservation({
  parkingSessionId,
  parkedSlotId,
  slots,
  observedSlotIds,
  rewardPoints,
  pendingSlotId,
  onObserve,
}: AdjacentSlotObservationProps) {
  const dismissalKey = `parksmart:adjacent-observation:dismissed:${parkingSessionId}`;
  const [adjacentSlots] = useState(() => {
    const observedSlots = new Set(observedSlotIds);
    return (
      adjacentParkingSlotIds(parkedSlotId)
        .map((slotId) => slots.find((slot) => slot.id === slotId))
        .filter(
          (slot): slot is ParkingSlot =>
            slot !== undefined &&
            slot.status !== "RESERVED" &&
            !observedSlots.has(slot.id),
        )
    );
  });
  const [expanded, setExpanded] = useState(false);
  const [dismissed, setDismissed] = useState(
    () =>
      typeof window !== "undefined" &&
      window.sessionStorage.getItem(dismissalKey) === "true",
  );
  const [step, setStep] = useState(0);
  const [result, setResult] = useState<SlotObservation | null>(null);
  const [error, setError] = useState(false);
  const submittingRef = useRef(false);

  if (dismissed || adjacentSlots.length === 0) return null;

  const current = adjacentSlots[step];
  const finished = step >= adjacentSlots.length;

  function dismiss() {
    window.sessionStorage.setItem(dismissalKey, "true");
    setDismissed(true);
  }

  function next() {
    setResult(null);
    setError(false);
    setStep((currentStep) => currentStep + 1);
  }

  async function answer(status: AdjacentSlotObservedStatus) {
    if (!current || submittingRef.current || pendingSlotId !== null) return;
    submittingRef.current = true;
    setError(false);
    const observation = await onObserve(current.id, status);
    if (observation) setResult(observation);
    else setError(true);
    submittingRef.current = false;
  }

  return (
    <section
      className="adjacent-slot-observation contribution-card"
      aria-labelledby="adjacent-observation-title"
    >
      {!expanded ? (
        <div className="contribution-invitation">
          <span className="contribution-icon" aria-hidden="true">♥</span>
          <div>
            <h2 id="adjacent-observation-title">
              Cùng giúp bãi xe chính xác hơn nhé!
            </h2>
            <p>
              Bạn giúp ParkSmart kiểm tra {adjacentSlots.length === 1 ? "ô bên cạnh xe" : "hai ô cạnh xe"} một chút nhé? Chỉ mất
              khoảng 5 giây và thông tin chính xác sẽ nhận điểm sau khi xác minh.
            </p>
            <div className="contribution-meta" aria-label="Thông tin đóng góp">
              <span>Khoảng 5 giây</span>
              <span className="reward-pill">
                Tối đa +{rewardPoints * adjacentSlots.length} điểm chờ xác minh
              </span>
            </div>
            <div className="contribution-actions">
              <button type="button" onClick={() => setExpanded(true)}>
                Giúp kiểm tra ngay
              </button>
              <button type="button" className="secondary-button" onClick={dismiss}>
                Để lúc khác
              </button>
            </div>
          </div>
        </div>
      ) : finished ? (
        <div role="status" aria-live="polite">
          <h2 id="adjacent-observation-title">Cảm ơn bạn đã giúp ParkSmart!</h2>
          <p>Các thông tin đã gửi sẽ được bộ phận vận hành xác minh.</p>
          <button type="button" className="secondary-button" onClick={dismiss}>
            Đóng
          </button>
        </div>
      ) : (
        <div className="contribution-question">
          <header>
            <div>
              <small>
                Tầng {current.floor_id.slice(1)} · Khu {current.zone_id} · {slotPosition(current.id, parkedSlotId)}
              </small>
              <h2 id="adjacent-observation-title">
                Bạn nhìn giúp ô {shortSlotName(current.id)} một chút nhé — ô này
                đang trống hay đã có xe?
              </h2>
            </div>
            <span className="contribution-progress" aria-label={`Bước ${step + 1} trên ${adjacentSlots.length}`}>
              {step + 1}/{adjacentSlots.length}
            </span>
          </header>

          {result ? (
            <div className="contribution-result" role="status" aria-live="polite">
              {result.reward_points > 0 ? (
                <p>
                  Cảm ơn bạn đã giúp cộng đồng ParkSmart! Thông tin về ô {shortSlotName(current.id)} đang chờ xác minh. +{result.reward_points} điểm sẽ được cộng nếu thông tin chính xác.
                </p>
              ) : (
                <p>
                  Cảm ơn bạn. Thông tin đang chờ xác minh. Bạn đã đạt giới hạn điểm hôm nay, nhưng đóng góp vẫn giúp cộng đồng.
                </p>
              )}
              <button type="button" onClick={next}>
                {step + 1 < adjacentSlots.length ? "Kiểm tra ô tiếp theo" : "Hoàn tất"}
              </button>
            </div>
          ) : (
            <>
              <div className="contribution-answer-grid">
                <button
                  type="button"
                  disabled={pendingSlotId !== null}
                  onClick={() => void answer("AVAILABLE")}
                >
                  Ô đang trống
                </button>
                <button
                  type="button"
                  disabled={pendingSlotId !== null}
                  onClick={() => void answer("OCCUPIED")}
                >
                  Đã có xe
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={pendingSlotId !== null}
                  onClick={next}
                >
                  Tôi không chắc
                </button>
              </div>
              <p role="status" aria-live="polite">
                {pendingSlotId === current.id ? "Đang gửi để chờ xác minh…" : ""}
              </p>
              {error && (
                <p className="report-error" role="alert">
                  Không thể gửi thông tin. Không có điểm nào được ghi nhận; vui lòng thử lại.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
