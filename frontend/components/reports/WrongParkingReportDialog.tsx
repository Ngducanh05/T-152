"use client";

import { useRef, useState } from "react";

import { ApiError, formatApiErrorForOperator } from "@/lib/api";
import { formatParkingLocation } from "@/lib/parking-display";
import type {
  ParkingSlot,
  WrongParkingReason,
  WrongParkingReport,
} from "@/lib/types";

export interface WrongParkingReportDraft {
  slotId: string;
  reasonCode: WrongParkingReason;
  observedPlateNumber: string | null;
  description: string | null;
  evidence: File | null;
}

interface WrongParkingReportDialogProps {
  slots: ParkingSlot[];
  initialSlotId?: string | null;
  rewardPoints: number;
  onClose: () => void;
  onSubmit: (draft: WrongParkingReportDraft) => Promise<WrongParkingReport>;
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

const MAX_IMAGE_BYTES = 5_000_000;
const ALLOWED_IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/heic",
  "image/heif",
]);

export function WrongParkingReportDialog({
  slots,
  initialSlotId = null,
  rewardPoints,
  onClose,
  onSubmit,
}: WrongParkingReportDialogProps) {
  const defaultSlotId = slots.some((slot) => slot.id === initialSlotId)
    ? initialSlotId ?? ""
    : "";
  const [slotId, setSlotId] = useState(defaultSlotId);
  const [observedPlateNumber, setObservedPlateNumber] = useState("");
  const [description, setDescription] = useState("");
  const [evidence, setEvidence] = useState<File | null>(null);
  const [selectedReason, setSelectedReason] =
    useState<WrongParkingReason | null>(null);
  const [pending, setPending] = useState(false);
  const [submittedReport, setSubmittedReport] =
    useState<WrongParkingReport | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const submittingRef = useRef(false);

  async function submitReport() {
    const normalizedDescription = description.trim();
    if (
      submittingRef.current ||
      !slotId ||
      !selectedReason ||
      (selectedReason === "OTHER" && normalizedDescription.length < 5)
    ) {
      return;
    }

    submittingRef.current = true;
    setPending(true);
    setErrorMessage(null);
    try {
      const report = await onSubmit({
        slotId,
        reasonCode: selectedReason,
        observedPlateNumber: observedPlateNumber.trim().toUpperCase() || null,
        description: normalizedDescription || null,
        evidence,
      });
      setSubmittedReport(report);
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError && error.code === "REPORT_DAILY_LIMIT_REACHED"
          ? "Bạn đã gửi hết số báo cáo cho hôm nay. Vui lòng thử lại vào ngày mai."
          : formatApiErrorForOperator(error, "Không thể gửi báo cáo lúc này."),
      );
    } finally {
      submittingRef.current = false;
      setPending(false);
    }
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

        {submittedReport ? (
          <div className="report-success" role="status" aria-live="polite">
            <b>Đã gửi báo cáo.</b>
            {submittedReport.reward_points > 0 ? (
              <p>+{submittedReport.reward_points} điểm đang chờ xác minh.</p>
            ) : submittedReport.duplicate_candidate_of_id ? (
              <p>Một report tương tự đang được xử lý nên report này không có điểm chờ.</p>
            ) : (
              <p>Bạn đã đạt giới hạn điểm hôm nay, nhưng report vẫn được bộ phận vận hành kiểm tra.</p>
            )}
            <button type="button" className="primary-button" onClick={requestClose}>
              Hoàn tất
            </button>
          </div>
        ) : (
          <div className="wrong-parking-report-form">
            <p>
              Chọn ô và lý do, sau đó bổ sung biển số, mô tả hoặc ảnh nếu có.
              Bạn luôn được xem lại thông tin trước khi gửi.
            </p>
            <p className="reward-condition">
              Report hợp lệ sau khi được bộ phận vận hành kiểm tra sẽ nhận +{rewardPoints} điểm ParkSmart.
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
              <legend>1. Chọn lý do</legend>
              {STANDARD_REASONS.map((reason) => (
                <button
                  key={reason.code}
                  type="button"
                  className={selectedReason === reason.code ? "is-selected" : ""}
                  aria-pressed={selectedReason === reason.code}
                  onClick={() => setSelectedReason(reason.code)}
                >
                  {reason.label}
                </button>
              ))}
              <button
                type="button"
                className={selectedReason === "OTHER" ? "is-selected" : ""}
                aria-pressed={selectedReason === "OTHER"}
                onClick={() => setSelectedReason("OTHER")}
              >
                Lý do khác
              </button>
            </fieldset>

            {selectedReason && (
              <>
                <div className="report-extra-fields">
                  <h3>2. Bổ sung thông tin xác minh</h3>
                  <p>Thông tin dưới đây không bắt buộc, nhưng sẽ giúp admin kiểm tra nhanh hơn.</p>
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
                  <label>
                    Ảnh hiện trường (không bắt buộc)
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
                      capture="environment"
                      disabled={pending}
                      onChange={(event) => {
                        const file = event.target.files?.[0] ?? null;
                        if (
                          file &&
                          (!ALLOWED_IMAGE_TYPES.has(file.type.toLowerCase()) ||
                            file.size <= 0 ||
                            file.size > MAX_IMAGE_BYTES)
                        ) {
                          setEvidence(null);
                          setErrorMessage(
                            "Ảnh phải đúng định dạng hình ảnh và có dung lượng tối đa 5 MB.",
                          );
                          return;
                        }
                        setEvidence(file);
                        setErrorMessage(null);
                      }}
                    />
                    <small>
                      {evidence
                        ? `Đã chọn: ${evidence.name}`
                        : "Thêm ảnh giúp bộ phận vận hành xác minh nhanh hơn."}
                    </small>
                    <small>
                      Ảnh chỉ được dùng để xác minh báo cáo. Không chụp khuôn mặt hoặc thông tin cá nhân không cần thiết.
                    </small>
                  </label>
                </div>
                <div className="report-submit-dock">
                  <button
                    type="button"
                    className="primary-button"
                    disabled={
                      pending ||
                      (selectedReason === "OTHER" && description.trim().length < 5)
                    }
                    onClick={() => void submitReport()}
                  >
                    {pending ? "Đang gửi báo cáo…" : "3. Gửi báo cáo"}
                  </button>
                </div>
              </>
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
