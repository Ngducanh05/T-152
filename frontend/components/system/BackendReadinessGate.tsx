"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { parkSmartApi } from "@/lib/api";

import styles from "./backend-readiness-gate.module.css";

export const WAKE_NOTICE_DELAY_MS = 3_000;
export const ATTEMPT_TIMEOUT_MS = 10_000;
export const RETRY_DELAY_MS = 4_000;
export const READINESS_DEADLINE_MS = 75_000;

type ReadinessStatus = "checking" | "waking" | "ready" | "unavailable";

interface BackendReadinessGateProps {
  children: ReactNode;
}

export function BackendReadinessGate({ children }: BackendReadinessGateProps) {
  const [status, setStatus] = useState<ReadinessStatus>("checking");
  const [cycle, setCycle] = useState(0);

  useEffect(() => {
    let active = true;
    let activeController: AbortController | null = null;
    const timers = new Set<ReturnType<typeof setTimeout>>();
    const startedAt = Date.now();

    const clearTimer = (timer: ReturnType<typeof setTimeout>) => {
      clearTimeout(timer);
      timers.delete(timer);
    };

    const schedule = (callback: () => void, delay: number) => {
      const timer = setTimeout(() => {
        timers.delete(timer);
        callback();
      }, delay);
      timers.add(timer);
      return timer;
    };

    const stopCycle = () => {
      active = false;
      activeController?.abort();
      activeController = null;
      for (const timer of timers) clearTimeout(timer);
      timers.clear();
    };

    const markUnavailable = () => {
      if (!active) return;
      activeController?.abort();
      activeController = null;
      for (const timer of timers) clearTimeout(timer);
      timers.clear();
      active = false;
      setStatus("unavailable");
    };

    const attempt = async () => {
      if (!active) return;

      const controller = new AbortController();
      activeController = controller;
      const timeout = schedule(() => controller.abort(), ATTEMPT_TIMEOUT_MS);

      try {
        await parkSmartApi.checkDatabaseHealth(controller.signal);
        clearTimer(timeout);
        if (!active) return;
        activeController = null;
        active = false;
        for (const timer of timers) clearTimeout(timer);
        timers.clear();
        setStatus("ready");
      } catch {
        clearTimer(timeout);
        if (!active) return;
        activeController = null;
        const elapsed = Date.now() - startedAt;
        if (elapsed + RETRY_DELAY_MS >= READINESS_DEADLINE_MS) return;
        schedule(() => void attempt(), RETRY_DELAY_MS);
      }
    };

    schedule(() => {
      if (active) setStatus("waking");
    }, WAKE_NOTICE_DELAY_MS);
    schedule(markUnavailable, READINESS_DEADLINE_MS);
    void attempt();

    return stopCycle;
  }, [cycle]);

  const retry = useCallback(() => {
    setStatus("checking");
    setCycle((current) => current + 1);
  }, []);

  if (status === "ready") return children;

  const unavailable = status === "unavailable";
  const message =
    status === "checking"
      ? "Đang kết nối với ParkSmart AI…"
      : status === "waking"
        ? "ParkSmart AI đang khởi động máy chủ miễn phí. Quá trình này có thể mất khoảng một phút."
        : "Không thể kết nối tới máy chủ ParkSmart. Vui lòng kiểm tra kết nối và thử lại.";

  return (
    <main className={styles.page}>
      <section
        className={styles.card}
        role={unavailable ? "alert" : "status"}
        aria-live={unavailable ? "assertive" : "polite"}
        aria-atomic="true"
      >
        <strong>ParkSmart AI</strong>
        <p>{message}</p>
        {unavailable && (
          <button type="button" onClick={retry}>
            Thử lại
          </button>
        )}
      </section>
    </main>
  );
}
