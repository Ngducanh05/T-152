"use client";

import { useState } from "react";

import { formatApiErrorForOperator, parkSmartApi } from "@/lib/api";

interface ObservationEvidencePanelProps {
  observationId: string;
}

/** Signed URLs stay component-local and are requested only after an admin asks to view evidence. */
export function ObservationEvidencePanel({ observationId }: ObservationEvidencePanelProps) {
  const [signedUrl, setSignedUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadEvidence() {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const result = await parkSmartApi.getAdminObservationEvidenceUrl(observationId);
      setSignedUrl(result.signed_url);
    } catch (loadError) {
      setError(formatApiErrorForOperator(loadError, "Không thể tải ảnh minh chứng."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="observation-evidence-panel" aria-label="Ảnh minh chứng quan sát">
      {!signedUrl && (
        <button type="button" className="secondary-button" disabled={loading} onClick={() => void loadEvidence()}>
          {loading ? "Đang tải ảnh…" : "Xem ảnh minh chứng"}
        </button>
      )}
      {error && (
        <div className="admin-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => void loadEvidence()} disabled={loading}>Thử lại</button>
        </div>
      )}
      {signedUrl && (
        <img
          className="observation-evidence-image"
          src={signedUrl}
          alt="Ảnh minh chứng do người dùng gửi"
        />
      )}
    </section>
  );
}
