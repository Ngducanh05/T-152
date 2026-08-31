"use client";

import { useState } from "react";

import { parkSmartApi } from "@/lib/api";
import type { SlotObservation } from "@/lib/types";

interface ObservationEvidencePanelProps {
  observation: SlotObservation;
}

export function ObservationEvidencePanel({
  observation,
}: ObservationEvidencePanelProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!observation.evidence_storage_path) return null;

  async function loadEvidence() {
    if (url || loading) return;

    setLoading(true);
    setError(null);
    try {
      const response = await parkSmartApi.getAdminObservationEvidenceUrl(
        observation.id,
      );
      setUrl(response.signed_url);
    } catch {
      setError("Không thể tải ảnh bằng chứng.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="observation-evidence-panel">
      <h3>Ảnh bằng chứng</h3>
      {url ? (
        <img
          className="observation-evidence-preview"
          src={url}
          alt="Bằng chứng quan sát"
        />
      ) : (
        <button
          type="button"
          disabled={loading}
          onClick={() => void loadEvidence()}
        >
          {loading ? "Đang tải…" : "Xem ảnh"}
        </button>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
