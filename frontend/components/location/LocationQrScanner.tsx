"use client";

import { useEffect, useRef, useState } from "react";

const LOCATION_QR_PREFIX = "parksmart:location:v1:";

interface LocationQrScannerProps {
  pending: boolean;
  errorMessage?: string | null;
  onClose: () => void;
  onScan: (qrPayload: string) => Promise<boolean>;
  onManualFallback: () => void;
}

export function LocationQrScanner({
  pending,
  errorMessage,
  onClose,
  onScan,
  onManualFallback,
}: LocationQrScannerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const controlsRef = useRef<{ stop: () => void } | null>(null);
  const streamRef = useRef<{ getTracks: () => { stop: () => void }[] } | null>(null);
  const onScanRef = useRef(onScan);
  const decodedRef = useRef(false);
  const mountedRef = useRef(true);
  const [state, setState] = useState<"opening" | "scanning" | "resolving" | "error">("opening");
  const [scannerError, setScannerError] = useState<string | null>(null);
  const [scannerAttempt, setScannerAttempt] = useState(0);

  function stopScanner() {
    const controls = controlsRef.current;
    controlsRef.current = null;
    try {
      controls?.stop();
    } catch {
      // Scanner teardown is best-effort and must remain safe to repeat.
    }
    const stream = streamRef.current ?? videoRef.current?.srcObject;
    streamRef.current = null;
    if (stream && "getTracks" in stream) {
      stream.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch {
          // A browser may already have released a track.
        }
      });
    }
    if (videoRef.current) videoRef.current.srcObject = null;
  }

  useEffect(() => {
    onScanRef.current = onScan;
  }, [onScan]);

  useEffect(() => {
    mountedRef.current = true;
    let cancelled = false;
    async function startScanner() {
      if (!navigator.mediaDevices?.getUserMedia || !videoRef.current) {
        setState("error");
        setScannerError("Trình duyệt không hỗ trợ quét QR bằng camera.");
        return;
      }
      try {
        const { BrowserQRCodeReader } = await import("@zxing/browser");
        if (cancelled || !videoRef.current) return;
        const reader = new BrowserQRCodeReader();
        const controls = await reader.decodeFromConstraints(
          { video: { facingMode: { ideal: "environment" } }, audio: false },
          videoRef.current,
          (result) => {
            const payload = result?.getText();
            if (!payload || decodedRef.current) return;
            decodedRef.current = true;
            if (!payload.trim().startsWith(LOCATION_QR_PREFIX)) {
              stopScanner();
              setState("error");
              setScannerError("Đây không phải QR vị trí ParkSmart.");
              return;
            }
            stopScanner();
            setState("resolving");
            void onScanRef.current(payload)
              .then((success) => {
                if (!success && mountedRef.current) {
                  setState("error");
                  setScannerError("Không thể xác định vị trí từ mã QR này.");
                }
              })
              .catch(() => {
                if (mountedRef.current) {
                  setState("error");
                  setScannerError("Không thể xác định vị trí từ mã QR này.");
                }
              });
          },
        );
        if (cancelled || decodedRef.current) {
          controls.stop();
          return;
        }
        const stream = videoRef.current?.srcObject;
        if (stream && "getTracks" in stream) {
          streamRef.current = stream;
        }
        controlsRef.current = controls;
        setState("scanning");
      } catch {
        if (!cancelled) {
          setState("error");
          setScannerError("Không thể truy cập camera.");
        }
      }
    }
    void startScanner();
    return () => {
      cancelled = true;
      mountedRef.current = false;
      stopScanner();
    };
  }, [scannerAttempt]);

  function retry() {
    decodedRef.current = false;
    setScannerError(null);
    setState("opening");
    setScannerAttempt((current) => current + 1);
  }

  function handleClose() {
    stopScanner();
    onClose();
  }

  function handleManualFallback() {
    stopScanner();
    onManualFallback();
  }

  const message =
    state === "opening"
      ? "Đang mở camera…"
      : state === "resolving" || pending
        ? "Đang xác định vị trí…"
        : state === "scanning"
          ? "Đưa mã QR vào khung hình"
          : scannerError;

  return (
    <div className="modal-backdrop" onClick={() => !pending && handleClose()}>
      <section
        className="modal location-qr-scanner"
        role="dialog"
        aria-modal="true"
        aria-labelledby="location-qr-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button type="button" className="modal-close" onClick={handleClose} disabled={pending} aria-label="Đóng quét QR">×</button>
        <p className="eyebrow green">VỊ TRÍ TRONG BÃI</p>
        <h2 id="location-qr-title">Quét QR vị trí</h2>
        <p>Đưa camera vào mã QR trên cột gần bạn.</p>
        <div className="location-qr-preview">
          <video ref={videoRef} muted playsInline aria-label="Camera quét QR vị trí" />
          <span aria-hidden="true" />
        </div>
        {message && <p className={state === "error" ? "location-api-error" : "location-pending"} role={state === "error" ? "alert" : "status"}>{message}</p>}
        {errorMessage && state !== "error" && <p className="location-api-error" role="alert">{errorMessage}</p>}
        {state === "error" && <button type="button" className="location-qr-retry" onClick={retry}>Quét lại</button>}
        <button type="button" className="location-qr-manual" onClick={handleManualFallback} disabled={pending}>Chọn vị trí thủ công</button>
      </section>
    </div>
  );
}
