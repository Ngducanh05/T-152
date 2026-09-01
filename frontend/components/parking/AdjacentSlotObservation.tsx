"use client";

import { useEffect, useRef, useState } from "react";

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
  pendingSlotId: string | null;
  onObserve: (
    slotId: string,
    status: AdjacentSlotObservedStatus,
    evidence?: File,
  ) => Promise<SlotObservation | null>;
}

const MAX_IMAGE_BYTES = 5_000_000;
const ACCEPTED_IMAGE_TYPES =
  "image/jpeg,image/png,image/webp,image/heic,image/heif";
const ALLOWED_IMAGE_TYPES = new Set(ACCEPTED_IMAGE_TYPES.split(","));
const PREVIEW_IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
]);

function shortSlotName(slotId: string) {
  return slotId.split("-").at(-1) ?? slotId;
}

function slotPosition(slotId: string, parkedSlotId: string) {
  const target = Number(slotId.slice(-2));
  const parked = Number(parkedSlotId.slice(-2));
  return target < parked ? "bên trái" : "bên phải";
}

function selectedStatusLabel(status: AdjacentSlotObservedStatus) {
  return status === "AVAILABLE" ? "Ô đang trống" : "Đã có xe";
}

function readableFileSize(size: number) {
  return size >= 1_000_000
    ? `${(size / 1_000_000).toFixed(1)} MB`
    : `${Math.ceil(size / 1_000)} KB`;
}

export function AdjacentSlotObservation({
  parkingSessionId,
  parkedSlotId,
  slots,
  observedSlotIds,
  pendingSlotId,
  onObserve,
}: AdjacentSlotObservationProps) {
  const dismissalKey = `parksmart:adjacent-observation:dismissed:${parkingSessionId}`;
  const [adjacentSlots] = useState(() => {
    const observedSlots = new Set(observedSlotIds);
    return adjacentParkingSlotIds(parkedSlotId)
      .map((slotId) => slots.find((slot) => slot.id === slotId))
      .filter(
        (slot): slot is ParkingSlot =>
          slot !== undefined &&
          slot.status !== "RESERVED" &&
          !observedSlots.has(slot.id),
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
  const [selectedStatus, setSelectedStatus] =
    useState<AdjacentSlotObservedStatus | null>(null);
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const submittingRef = useRef(false);
  const previewUrlRef = useRef<string | null>(null);
  const cameraInputRef = useRef<HTMLInputElement | null>(null);
  const galleryInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    };
  }, []);

  if (dismissed || adjacentSlots.length === 0) return null;

  const current = adjacentSlots[step];
  const finished = step >= adjacentSlots.length;

  function revokePreview() {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
    setPreviewUrl(null);
  }

  function clearEvidence() {
    revokePreview();
    setEvidenceFile(null);
    setEvidenceError(null);
    if (cameraInputRef.current) cameraInputRef.current.value = "";
    if (galleryInputRef.current) galleryInputRef.current.value = "";
  }

  function clearReview() {
    clearEvidence();
    setSelectedStatus(null);
  }

  function dismiss() {
    clearReview();
    window.sessionStorage.setItem(dismissalKey, "true");
    setDismissed(true);
  }

  function next() {
    clearReview();
    setResult(null);
    setError(false);
    setStep((currentStep) => currentStep + 1);
  }

  function selectEvidence(file: File | null) {
    if (!file) {
      clearEvidence();
      return;
    }

    const contentType = file.type.toLowerCase();
    if (
      !ALLOWED_IMAGE_TYPES.has(contentType) ||
      file.size <= 0 ||
      file.size > MAX_IMAGE_BYTES
    ) {
      setEvidenceError(
        "Ảnh phải là JPEG, PNG, WebP, HEIC hoặc HEIF và không vượt quá 5 MB.",
      );
      return;
    }

    revokePreview();
    setEvidenceFile(file);
    setEvidenceError(null);
    if (PREVIEW_IMAGE_TYPES.has(contentType)) {
      try {
        const nextPreview = URL.createObjectURL(file);
        previewUrlRef.current = nextPreview;
        setPreviewUrl(nextPreview);
      } catch {
        setPreviewUrl(null);
      }
    }
  }

  function evidenceChange(event: React.ChangeEvent<HTMLInputElement>) {
    selectEvidence(event.target.files?.[0] ?? null);
  }

  async function submitObservation() {
    if (
      !current ||
      !selectedStatus ||
      submittingRef.current ||
      pendingSlotId !== null
    ) {
      return;
    }

    submittingRef.current = true;
    setError(false);
    try {
      const observation = await onObserve(
        current.id,
        selectedStatus,
        evidenceFile ?? undefined,
      );
      if (!observation) {
        setError(true);
        return;
      }
      clearReview();
      setResult(observation);
    } catch {
      setError(true);
    } finally {
      submittingRef.current = false;
    }
  }

  return (
    <section
      className="adjacent-slot-observation contribution-card"
      aria-labelledby="adjacent-observation-title"
    >
      {!expanded ? (
        <div className="contribution-invitation">
          <span className="contribution-icon" aria-hidden="true">
            ♥
          </span>
          <div>
            <h2 id="adjacent-observation-title">
              Cùng giúp bãi xe chính xác hơn nhé!
            </h2>
            <p>
              Bạn giúp ParkSmart kiểm tra{" "}
              {adjacentSlots.length === 1
                ? "ô bên cạnh xe"
                : "hai ô cạnh xe"}{" "}
              một chút nhé? Chỉ mất khoảng 5 giây.
            </p>
            <div className="contribution-meta" aria-label="Thông tin đóng góp">
              <span>Khoảng 5 giây</span>
              <span className="reward-pill">
                Đóng góp hợp lệ có thể nhận ParkSmart Points sau khi được xác minh.
              </span>
            </div>
            <div className="contribution-actions">
              <button type="button" onClick={() => setExpanded(true)}>
                Giúp kiểm tra ngay
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={dismiss}
              >
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
                Tầng {current.floor_id.slice(1)} · Khu {current.zone_id} ·{" "}
                {slotPosition(current.id, parkedSlotId)}
              </small>
              <h2 id="adjacent-observation-title">
                Bạn nhìn giúp ô {shortSlotName(current.id)} một chút nhé — ô này
                đang trống hay đã có xe?
              </h2>
            </div>
            <span
              className="contribution-progress"
              aria-label={`Bước ${step + 1} trên ${adjacentSlots.length}`}
            >
              {step + 1}/{adjacentSlots.length}
            </span>
          </header>

          {result ? (
            <div className="contribution-result" role="status" aria-live="polite">
              {result.reward_points > 0 ? (
                <p>
                  Cảm ơn bạn đã giúp cộng đồng ParkSmart! Thông tin đang chờ xác
                  minh. Bạn có thể theo dõi trong ParkSmart Points.
                </p>
              ) : (
                <p>
                  Cảm ơn bạn. Thông tin đang chờ xác minh. Bạn đã đạt giới hạn
                  điểm hôm nay, nhưng đóng góp vẫn giúp cộng đồng.
                </p>
              )}
              <button type="button" onClick={next}>
                {step + 1 < adjacentSlots.length
                  ? "Kiểm tra ô tiếp theo"
                  : "Hoàn tất"}
              </button>
            </div>
          ) : selectedStatus ? (
            <section className="observation-review" aria-labelledby="observation-review-title">
              <h3 id="observation-review-title">Xem lại đóng góp</h3>
              <div className="observation-review-summary">
                <span className="observation-review-label">
                  Trạng thái đã chọn:
                </span>
                <strong>{selectedStatusLabel(selectedStatus)}</strong>
              </div>
              <section className="observation-evidence evidence-picker">
                <div className="evidence-picker-heading">
                  <h4>Ảnh xác minh</h4>
                  <span>Không bắt buộc</span>
                </div>
                <p className="evidence-picker-help">
                  JPEG, PNG, WebP, HEIC/HEIF · tối đa 5 MB
                </p>
                <input
                  ref={cameraInputRef}
                  className="sr-only"
                  type="file"
                  aria-label="Chụp ảnh quan sát"
                  accept={ACCEPTED_IMAGE_TYPES}
                  capture="environment"
                  onChange={evidenceChange}
                />
                <input
                  ref={galleryInputRef}
                  className="sr-only"
                  type="file"
                  aria-label="Chọn ảnh quan sát từ thư viện"
                  accept={ACCEPTED_IMAGE_TYPES}
                  onChange={evidenceChange}
                />
                <div className="observation-evidence-actions evidence-picker-actions">
                  <button
                    type="button"
                    className="evidence-picker-action evidence-picker-camera"
                    onClick={() => cameraInputRef.current?.click()}
                  >
                    Chụp ảnh
                  </button>
                  <button
                    type="button"
                    className="evidence-picker-action"
                    onClick={() => galleryInputRef.current?.click()}
                  >
                    {evidenceFile ? "Đổi ảnh" : "Chọn từ thư viện"}
                  </button>
                  {evidenceFile && (
                    <button
                      type="button"
                      className="evidence-picker-action evidence-picker-remove"
                      onClick={clearEvidence}
                    >
                      Xóa ảnh
                    </button>
                  )}
                </div>
                {evidenceFile && (
                  <div
                    className={`observation-evidence-selected evidence-picker-selected${
                      previewUrl ? " has-preview" : ""
                    }`}
                  >
                    {previewUrl && (
                      <img
                        className="observation-evidence-preview evidence-picker-preview"
                        src={previewUrl}
                        alt="Ảnh quan sát đã chọn"
                      />
                    )}
                    <div className="evidence-picker-copy">
                      <p className="evidence-picker-file-name">
                        {evidenceFile.name}
                      </p>
                      <small className="evidence-picker-meta">
                        {evidenceFile.type} · {readableFileSize(evidenceFile.size)}
                      </small>
                    </div>
                  </div>
                )}
                {evidenceError && (
                  <p className="report-error" role="alert">
                    {evidenceError}
                  </p>
                )}
              </section>
              <div className="contribution-answer-grid">
                <button
                  type="button"
                  disabled={pendingSlotId !== null}
                  onClick={() => void submitObservation()}
                >
                  {pendingSlotId === current.id ? "Đang gửi…" : "Gửi đóng góp"}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={pendingSlotId !== null}
                  onClick={() => {
                    clearReview();
                    setError(false);
                  }}
                >
                  Chọn lại
                </button>
              </div>
              {error && (
                <p className="report-error" role="alert">
                  Không thể gửi thông tin. Không có điểm nào được ghi nhận; vui
                  lòng thử lại.
                </p>
              )}
            </section>
          ) : (
            <>
              <div className="contribution-answer-grid">
                <button
                  type="button"
                  disabled={pendingSlotId !== null}
                  onClick={() => setSelectedStatus("AVAILABLE")}
                >
                  Ô đang trống
                </button>
                <button
                  type="button"
                  disabled={pendingSlotId !== null}
                  onClick={() => setSelectedStatus("OCCUPIED")}
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
            </>
          )}
        </div>
      )}
    </section>
  );
}
