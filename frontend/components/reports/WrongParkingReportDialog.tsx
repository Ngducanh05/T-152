"use client";

import { useRef, useState } from "react";

import { formatApiErrorForOperator } from "@/lib/api";
import { formatParkingLocation } from "@/lib/parking-display";
import type { ParkingSlot, WrongParkingReason } from "@/lib/types";

export interface WrongParkingReportDraft {
  slotId: string;
  reasonCode: WrongParkingReason;
  observedPlateNumber: string | null;
  description: string | null;
}

interface WrongParkingReportDialogProps {
  slots: ParkingSlot[];
  initialSlotId?: string | null;
  onClose: () => void;
  onSubmit: (draft: WrongParkingReportDraft) => Promise<void>;
}

const STANDARD_REASONS: Array<{
  code: Exclude<WrongParkingReason, "OTHER">;
  label: string;
}> = [
  { code: "WRONG_SLOT", label: "Xe đỗ sai ô" },
  { code: "CROSSED_LINE", label: "Xe đỗ chéo vạch" },
  { code: "BLOCKING_ACCESS", label: "Xe chắn lối đi" },
  { code: "OCCUPYING_CHARGER", label: "Xe chiếm chỗ sạc" },
];

export function WrongParkingReportDialog({
  slots,
  initialSlotId = null,
  onClose,
  onSubmit,
}: WrongParkingReportDialogProps) {
  const defaultSlotId = slots.some((slot) => slot.id === initialSlotId)
    ? initialSlotId ?? ""
    : "";
  const [slotId, setSlotId] = useState(defaultSlotId);
  const [observedPlateNumber, setObservedPlateNumber] = useState("");
  const [description, setDescription] = useState("");
  const [showMore, setShowMore] = useState(false);
  const [selectedReason, setSelectedReason] =
    useState<WrongParkingReason | null>(null);
  const [pending, setPending] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const submittingRef = useRef(false);

  async function submitReason(reasonCode: WrongParkingReason) {
    const normalizedDescription = description.trim();
    if (
      submittingRef.current ||
      !slotId ||
      (reasonCode === "OTHER" && normalizedDescription.length < 5)
    ) {
      return;
    }

    submittingRef.current = true;
    setSelectedReason(reasonCode);
    setPending(true);
    setErrorMessage(null);
    try {
      await onSubmit({
        slotId,
        reasonCode,
        observedPlateNumber: observedPlateNumber.trim().toUpperCase() || null,
        description: normalizedDescription || null,
      });
      setSubmitted(true);
    } catch (error) {
      setErrorMessage(
        formatApiErrorForOperator(error, "Không thể gửi báo cáo lúc này."),
      );
    } finally {
      submittingRef.current = false;
      setPending(false);
    }
  }

  function chooseOtherReason() {
    setSelectedReason("OTHER");
    setShowMore(true);
  }

  function requestClose() {
    if (!pending) onClose();
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
        className="modal wrong-parking-report-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="wrong-parking-report-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          className="modal-close"
          onClick={requestClose}
          aria-label="Đóng báo cáo"
          disabled={pending}
        >
          ×
        </button>
        <p className="eyebrow green">PHẢN ÁNH TRONG BÃI XE</p>
        <h2 id="wrong-parking-report-title">Báo xe đỗ sai vị trí</h2>

        {submitted ? (
          <div className="report-success" role="status" aria-live="polite">
            <b>Đã gửi báo cáo.</b>
            <p>Bộ phận vận hành sẽ kiểm tra thông tin bạn cung cấp.</p>
            <button type="button" className="primary-button" onClick={requestClose}>
              Hoàn tất
            </button>
          </div>
        ) : (
          <div className="wrong-parking-report-form">
            <p>
              Chọn ô và lý do. Chạm vào một lý do chuẩn sẽ gửi báo cáo ngay;
              trạng thái ô đỗ không bị thay đổi.
            </p>
            <label>
              Ô cần phản ánh
              <select
                value={slotId}
                onChange={(event) => setSlotId(event.target.value)}
                disabled={pending || slots.length === 0}
              >
                <option value="">Chọn ô đỗ</option>
                {slots.map((slot) => (
                  <option key={slot.id} value={slot.id}>
                    {formatParkingLocation(slot.id)}
                  </option>
                ))}
              </select>
            </label>

            <fieldset className="report-reasons" disabled={pending || !slotId}>
              <legend>Chọn lý do để gửi</legend>
              {STANDARD_REASONS.map((reason) => (
                <button
                  key={reason.code}
                  type="button"
                  onClick={() => void submitReason(reason.code)}
                >
                  {pending && selectedReason === reason.code
                    ? "Đang gửi…"
                    : `Gửi: ${reason.label}`}
                </button>
              ))}
              <button
                type="button"
                aria-expanded={showMore && selectedReason === "OTHER"}
                onClick={chooseOtherReason}
              >
                Lý do khác
              </button>
            </fieldset>

            <button
              type="button"
              className="report-more-toggle"
              aria-expanded={showMore}
              onClick={() => setShowMore((current) => !current)}
              disabled={pending}
            >
              {showMore ? "Ẩn thông tin thêm" : "Thêm thông tin"}
            </button>

            {showMore && (
              <div className="report-extra-fields">
                <label>
                  Biển số quan sát được (không bắt buộc)
                  <input
                    value={observedPlateNumber}
                    onChange={(event) =>
                      setObservedPlateNumber(event.target.value.toUpperCase())
                    }
                    maxLength={32}
                    placeholder="Ví dụ: 51A-123.45"
                    disabled={pending}
                  />
                </label>
                <label>
                  Mô tả {selectedReason === "OTHER" ? "(bắt buộc)" : "(không bắt buộc)"}
                  <textarea
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    minLength={selectedReason === "OTHER" ? 5 : undefined}
                    maxLength={500}
                    placeholder="Thêm chi tiết giúp bộ phận vận hành kiểm tra."
                    disabled={pending}
                  />
                  <small>{description.length}/500 ký tự</small>
                </label>
                {selectedReason === "OTHER" && (
                  <button
                    type="button"
                    className="primary-button"
                    disabled={pending || description.trim().length < 5}
                    onClick={() => void submitReason("OTHER")}
                  >
                    {pending ? "Đang gửi…" : "Gửi báo cáo lý do khác"}
                  </button>
                )}
              </div>
            )}

            {errorMessage && <p className="report-error" role="alert">{errorMessage}</p>}
            <p className="report-submit-status" role="status" aria-live="polite">
              {pending ? "Báo cáo đang được gửi. Vui lòng chờ." : ""}
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
