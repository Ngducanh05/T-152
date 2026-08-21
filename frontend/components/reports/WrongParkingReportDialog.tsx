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
  evidence: File;
}

interface WrongParkingReportDialogProps {
  slots: ParkingSlot[];
  initialSlotId?: string | null;
  onClose: () => void;
  onSubmit: (draft: WrongParkingReportDraft) => Promise<void>;
}

const MAX_IMAGE_BYTES = 5_000_000;
const REASONS: Array<{ code: WrongParkingReason; label: string }> = [
  { code: "WRONG_SLOT", label: "Xe do sai o" },
  { code: "CROSSED_LINE", label: "Xe do cheo vach" },
  { code: "BLOCKING_ACCESS", label: "Xe chan loi di" },
  { code: "OCCUPYING_CHARGER", label: "Xe chiem cho sac" },
  { code: "OTHER", label: "Ly do khac" },
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
  const [reasonCode, setReasonCode] =
    useState<WrongParkingReason>("CROSSED_LINE");
  const [observedPlateNumber, setObservedPlateNumber] = useState("");
  const [description, setDescription] = useState("");
  const [evidence, setEvidence] = useState<File | null>(null);
  const [pending, setPending] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const submittingRef = useRef(false);

  const normalizedDescription = description.trim();
  const evidenceValid =
    evidence &&
    evidence.type.startsWith("image/") &&
    evidence.size > 0 &&
    evidence.size <= MAX_IMAGE_BYTES;
  const canSubmit =
    Boolean(slotId) &&
    Boolean(evidenceValid) &&
    (reasonCode !== "OTHER" || normalizedDescription.length >= 5);

  async function submit() {
    if (submittingRef.current || !canSubmit || !evidence) return;
    submittingRef.current = true;
    setPending(true);
    setErrorMessage(null);
    try {
      await onSubmit({
        slotId,
        reasonCode,
        observedPlateNumber: observedPlateNumber.trim().toUpperCase() || null,
        description: normalizedDescription || null,
        evidence,
      });
      setSubmitted(true);
    } catch (error) {
      setErrorMessage(
        formatApiErrorForOperator(error, "Khong the gui bao cao luc nay."),
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
          aria-label="Dong bao cao"
          disabled={pending}
        >
          x
        </button>
        <p className="eyebrow green">PHAN ANH TRONG BAI XE</p>
        <h2 id="wrong-parking-report-title">Bao xe do sai vi tri</h2>

        {submitted ? (
          <div className="report-success" role="status" aria-live="polite">
            <b>Da gui bao cao.</b>
            <p>Bo phan van hanh se kiem tra thong tin ban cung cap.</p>
            <button type="button" className="primary-button" onClick={requestClose}>
              Hoan tat
            </button>
          </div>
        ) : (
          <div className="wrong-parking-report-form">
            <label>
              O can phan anh
              <select
                value={slotId}
                onChange={(event) => setSlotId(event.target.value)}
                disabled={pending || slots.length === 0}
              >
                <option value="">Chon o do</option>
                {slots.map((slot) => (
                  <option key={slot.id} value={slot.id}>
                    {formatParkingLocation(slot.id)}
                  </option>
                ))}
              </select>
            </label>

            <fieldset className="report-reasons" disabled={pending}>
              <legend>Ly do</legend>
              {REASONS.map((reason) => (
                <button
                  key={reason.code}
                  type="button"
                  aria-pressed={reasonCode === reason.code}
                  onClick={() => setReasonCode(reason.code)}
                >
                  {reason.label}
                </button>
              ))}
            </fieldset>

            <label>
              Anh bang chung
              <input
                type="file"
                accept="image/*"
                capture="environment"
                disabled={pending}
                onChange={(event) => {
                  const file = event.target.files?.[0] ?? null;
                  setEvidence(file);
                  if (
                    file &&
                    (!file.type.startsWith("image/") || file.size > MAX_IMAGE_BYTES)
                  ) {
                    setErrorMessage("Anh phai dung dinh dang image/* va toi da 5 MB.");
                  } else {
                    setErrorMessage(null);
                  }
                }}
              />
            </label>

            <label>
              Bien so quan sat duoc (khong bat buoc)
              <input
                value={observedPlateNumber}
                onChange={(event) =>
                  setObservedPlateNumber(event.target.value.toUpperCase())
                }
                maxLength={32}
                placeholder="VD: 51A-123.45"
                disabled={pending}
              />
            </label>

            <label>
              Mo ta {reasonCode === "OTHER" ? "(bat buoc)" : "(khong bat buoc)"}
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                minLength={reasonCode === "OTHER" ? 5 : undefined}
                maxLength={500}
                placeholder="Them chi tiet giup bo phan van hanh kiem tra."
                disabled={pending}
              />
              <small>{description.length}/500 ky tu</small>
            </label>

            {errorMessage && <p className="report-error" role="alert">{errorMessage}</p>}
            <button
              type="button"
              className="primary-button"
              disabled={pending || !canSubmit}
              onClick={() => void submit()}
            >
              {pending ? "Dang gui..." : "Gui bao cao"}
            </button>
            <p className="report-submit-status" role="status" aria-live="polite">
              {pending ? "Bao cao dang duoc gui. Vui long cho." : ""}
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
