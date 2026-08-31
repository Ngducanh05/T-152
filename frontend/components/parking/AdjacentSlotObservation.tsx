"use client";

import { useEffect, useRef, useState } from "react";

import { adjacentParkingSlotIds } from "@/lib/adjacent-parking-slots";
import type {
  AdjacentSlotObservedStatus,
  FloorScopedId,
  ParkingSlot,
  SlotObservation,
} from "@/lib/types";

const MAX_IMAGE_BYTES = 5_000_000;
const ALLOWED_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"]);

interface AdjacentSlotObservationProps {
  parkingSessionId: string;
  parkedSlotId: string;
  slots: ParkingSlot[];
  observedSlotIds: string[];
  pendingSlotId: string | null;
  onObserve: (
    slotId: FloorScopedId,
    status: AdjacentSlotObservedStatus,
    evidence?: File | null,
  ) => Promise<SlotObservation | null>;
}

function shortSlotName(slotId: string) { return slotId.split("-").at(-1) ?? slotId; }
function slotPosition(slotId: string, parkedSlotId: string) { return Number(slotId.slice(-2)) < Number(parkedSlotId.slice(-2)) ? "bên trái" : "bên phải"; }

export function AdjacentSlotObservation({ parkingSessionId, parkedSlotId, slots, observedSlotIds, pendingSlotId, onObserve }: AdjacentSlotObservationProps) {
  const dismissalKey = `parksmart:adjacent-observation:dismissed:${parkingSessionId}`;
  const [adjacentSlots] = useState(() => {
    const observed = new Set(observedSlotIds);
    return adjacentParkingSlotIds(parkedSlotId)
      .map((id) => slots.find((slot) => slot.id === id))
      .filter(
        (slot): slot is ParkingSlot =>
          slot !== undefined && slot.status !== "RESERVED" && !observed.has(slot.id),
      );
  });
  const [expanded, setExpanded] = useState(false);
  const [dismissed, setDismissed] = useState(() => typeof window !== "undefined" && window.sessionStorage.getItem(dismissalKey) === "true");
  const [step, setStep] = useState(0);
  const [selectedStatus, setSelectedStatus] = useState<AdjacentSlotObservedStatus | null>(null);
  const [evidence, setEvidence] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewUnavailable, setPreviewUnavailable] = useState(false);
  const [result, setResult] = useState<SlotObservation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const galleryInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  if (dismissed || adjacentSlots.length === 0) return null;
  const current = adjacentSlots[step];
  const finished = step >= adjacentSlots.length;
  const pending = pendingSlotId === current?.id || submitting;

  function clearDraft() {
    setSelectedStatus(null); setEvidence(null); setPreviewUrl(null); setPreviewUnavailable(false); setError(null); setResult(null);
  }
  function dismiss() { window.sessionStorage.setItem(dismissalKey, "true"); setDismissed(true); }
  function next() { clearDraft(); setStep((value) => value + 1); }
  function chooseStatus(status: AdjacentSlotObservedStatus) { if (!pending) { setSelectedStatus(status); setError(null); } }
  function selectEvidence(file: File | null) {
    if (file && (!ALLOWED_IMAGE_TYPES.has(file.type.toLowerCase()) || file.size <= 0 || file.size > MAX_IMAGE_BYTES)) {
      setError("Ảnh phải thuộc định dạng được hỗ trợ, không rỗng và tối đa 5 MB."); return;
    }
    setEvidence(file); setPreviewUnavailable(false); setError(null);
    try { setPreviewUrl(file ? URL.createObjectURL(file) : null); } catch { setPreviewUrl(null); setPreviewUnavailable(Boolean(file)); }
  }
  async function submit() {
    if (!current || !selectedStatus || pending || submittingRef.current) return;
    submittingRef.current = true; setSubmitting(true); setError(null);
    try { const observation = await onObserve(current.id, selectedStatus, evidence); if (observation) setResult(observation); else setError("Không thể gửi thông tin. Vui lòng thử lại."); }
    finally { submittingRef.current = false; setSubmitting(false); }
  }

  return <section className="adjacent-slot-observation contribution-card" aria-labelledby="adjacent-observation-title">
    {!expanded ? <div className="contribution-invitation"><span className="contribution-icon" aria-hidden="true">♥</span><div><h2 id="adjacent-observation-title">Cùng giúp bãi xe chính xác hơn nhé!</h2><p>Bạn giúp ParkSmart kiểm tra {adjacentSlots.length === 1 ? "ô bên cạnh xe" : "hai ô cạnh xe"} một chút nhé? Thông tin đã xác minh sẽ được ghi nhận trong ParkSmart Points.</p><div className="contribution-actions"><button type="button" onClick={() => setExpanded(true)}>Giúp kiểm tra ngay</button><button type="button" className="secondary-button" onClick={dismiss}>Để lúc khác</button></div></div></div> : finished ? <div role="status" aria-live="polite"><h2 id="adjacent-observation-title">Cảm ơn bạn đã giúp ParkSmart!</h2><p>Các thông tin đã gửi sẽ được bộ phận vận hành xác minh.</p><button type="button" className="secondary-button" onClick={dismiss}>Đóng</button></div> : <div className="contribution-question">
      <header><div><small>Tầng {current.floor_id.slice(1)} · Khu {current.zone_id} · {slotPosition(current.id, parkedSlotId)}</small><h2 id="adjacent-observation-title">Bạn nhìn giúp ô {shortSlotName(current.id)} một chút nhé — ô này đang trống hay đã có xe?</h2></div><span className="contribution-progress" aria-label={`Bước ${step + 1} trên ${adjacentSlots.length}`}>{step + 1}/{adjacentSlots.length}</span></header>
      {result ? <div className="contribution-result" role="status" aria-live="polite"><p>Đóng góp đã được gửi và đang chờ xác minh. Bạn có thể theo dõi trong ParkSmart Points.</p><button type="button" onClick={next}>{step + 1 < adjacentSlots.length ? "Kiểm tra ô tiếp theo" : "Hoàn tất"}</button></div> : !selectedStatus ? <div className="contribution-answer-grid"><button type="button" disabled={pending} onClick={() => chooseStatus("AVAILABLE")}>Ô đang trống</button><button type="button" disabled={pending} onClick={() => chooseStatus("OCCUPIED")}>Đã có xe</button><button type="button" className="secondary-button" disabled={pending} onClick={next}>Tôi không chắc</button></div> : <div className="adjacent-observation-review"><p>Bạn chọn: <b>{selectedStatus === "AVAILABLE" ? "Ô đang trống" : "Đã có xe"}</b></p><input ref={cameraInputRef} className="visually-hidden" type="file" accept="image/*" capture="environment" onChange={(event) => selectEvidence(event.target.files?.[0] ?? null)} disabled={pending}/><input ref={galleryInputRef} className="visually-hidden" type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" onChange={(event) => selectEvidence(event.target.files?.[0] ?? null)} disabled={pending}/><div className="report-evidence-actions"><button type="button" disabled={pending} onClick={() => cameraInputRef.current?.click()}>{evidence ? "Chụp lại" : "Chụp ảnh"}</button><button type="button" disabled={pending} onClick={() => galleryInputRef.current?.click()}>{evidence ? "Đổi ảnh" : "Thêm ảnh"}</button>{evidence && <button type="button" disabled={pending} onClick={() => selectEvidence(null)}>Xóa ảnh</button>}</div>{evidence && <div className="report-evidence-selected">{previewUrl && !previewUnavailable && <img src={previewUrl} alt="Ảnh minh chứng đã chọn" onError={() => setPreviewUnavailable(true)}/>}<small>Đã chọn: {evidence.name} · {(evidence.size / 1_000_000).toFixed(1)} MB{previewUnavailable ? " · Trình duyệt không thể xem trước ảnh này." : ""}</small></div>}<div className="adjacent-review-actions"><button type="button" className="secondary-button" disabled={pending} onClick={() => setSelectedStatus(null)}>Đổi trạng thái</button><button type="button" className="primary-button" disabled={pending} onClick={() => void submit()}>{pending ? "Đang gửi để chờ xác minh…" : "Gửi đóng góp"}</button></div></div>}
      <p role="status" aria-live="polite">{pending ? "Đang gửi để chờ xác minh…" : ""}</p>{error && <p className="report-error" role="alert">{error}</p>}
    </div>}
  </section>;
}
