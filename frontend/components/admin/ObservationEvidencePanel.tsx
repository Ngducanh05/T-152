"use client";

import { useEffect, useRef, useState } from "react";

import { parkSmartApi } from "@/lib/api";
import type { SlotObservation } from "@/lib/types";

interface ObservationEvidencePanelProps {
  observation: SlotObservation;
}

interface EvidenceState {
  observationIdentity: string;
  url: string | null;
  error: string | null;
  loading: boolean;
}

export function ObservationEvidencePanel({
  observation,
}: ObservationEvidencePanelProps) {
  const observationIdentity = `${observation.id}:${observation.evidence_storage_path ?? ""}`;
  const [evidenceState, setEvidenceState] = useState<EvidenceState>({
    observationIdentity,
    url: null,
    error: null,
    loading: false,
  });
  const requestGenerationRef = useRef(0);

  const { url, error, loading } =
    evidenceState.observationIdentity === observationIdentity
      ? evidenceState
      : { url: null, error: null, loading: false };

  useEffect(() => {
    requestGenerationRef.current += 1;
  }, [observation.id, observation.evidence_storage_path]);

  if (!observation.evidence_storage_path) return null;

  async function loadEvidence() {
    if (url || loading || !observation.evidence_storage_path) return;

    const requestGeneration = requestGenerationRef.current;
    const observationId = observation.id;
    setEvidenceState({
      observationIdentity,
      url: null,
      error: null,
      loading: true,
    });
    try {
      const response = await parkSmartApi.getAdminObservationEvidenceUrl(
        observationId,
      );
      if (requestGeneration !== requestGenerationRef.current) return;
      setEvidenceState({
        observationIdentity,
        url: response.signed_url,
        error: null,
        loading: true,
      });
    } catch {
      if (requestGeneration !== requestGenerationRef.current) return;
      setEvidenceState({
        observationIdentity,
        url: null,
        error: "Không thể tải ảnh bằng chứng.",
        loading: true,
      });
    } finally {
      if (requestGeneration === requestGenerationRef.current) {
        setEvidenceState((current) =>
          current.observationIdentity === observationIdentity
            ? { ...current, loading: false }
            : current,
        );
      }
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
