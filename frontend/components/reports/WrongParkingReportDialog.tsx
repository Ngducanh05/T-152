"use client";

import { FormEvent, useRef, useState } from "react";

import { formatApiErrorForOperator } from "@/lib/api";
import { formatParkingLocation } from "@/lib/parking-display";
import type { ParkingSlot } from "@/lib/types";

export interface WrongParkingReportDraft {
  slotId: string;
  observedPlateNumber: string | null;
  description: string;
}

interface WrongParkingReportDialogProps {
  slots: ParkingSlot[];
  initialSlotId?: string | null;
  onClose: () => void;
  onSubmit: (draft: WrongParkingReportDraft) => Promise<void>;
}

export function WrongParkingReportDialog({
  slots,
  initialSlotId = null,
  onClose,
  onSubmit,
}: WrongParkingReportDialogProps) {
  const defaultSlotId = slots.some((slot) => slot.id === initialSlotId)
    ? initialSlotId ?? ""
    : slots[0]?.id ?? "";
  const [slotId, setSlotId] = useState(defaultSlotId);
  const [observedPlateNumber, setObservedPlateNumber] = useState("");
  const [description, setDescription] = useState("");
  const [pending, setPending] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const submittingRef = useRef(false);

  async function submitReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedDescription = description.trim();
    if (
      submittingRef.current ||
      !slotId ||
      normalizedDescription.length < 5
    ) {
      return;
    }

    submittingRef.current = true;
    setPending(true);
    setErrorMessage(null);
    try {
      await onSubmit({
        slotId,
        observedPlateNumber: observedPlateNumber.trim().toUpperCase() || null,
        description: normalizedDescription,
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
          <form className="wrong-parking-report-form" onSubmit={submitReport}>
            <p>
              Chọn ô đang có xe đỗ sai và mô tả ngắn tình trạng quan sát được.
              Báo cáo không tự thay đổi trạng thái ô đỗ.
            </p>
            <label>
              Ô cần phản ánh
              <select
                value={slotId}
                onChange={(event) => setSlotId(event.target.value)}
                disabled={pending || slots.length === 0}
              >
                {slots.map((slot) => (
                  <option key={slot.id} value={slot.id}>
                    {formatParkingLocation(slot.id)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Biển số hoặc mã xe quan sát được (không bắt buộc)
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
              Mô tả tình trạng
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                minLength={5}
                maxLength={500}
                placeholder="Ví dụ: Xe đỗ chéo và lấn sang ô bên cạnh."
                disabled={pending}
                required
              />
              <small>{description.length}/500 ký tự</small>
            </label>
            {errorMessage && <p className="report-error" role="alert">{errorMessage}</p>}
            <button
              type="submit"
              className="primary-button"
              disabled={pending || !slotId || description.trim().length < 5}
            >
              {pending ? "Đang gửi…" : "Gửi báo cáo"}
            </button>
          </form>
        )}
      </section>
    </div>
  );
}
