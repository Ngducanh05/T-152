"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ReportDetailDrawer,
  type PendingReportMutation,
  type ReportMutationAction,
} from "@/components/admin/ReportDetailDrawer";
import { ParkingMap } from "@/components/parking/ParkingMap";
import { useParkSmartData } from "@/hooks/use-parksmart-data";
import { ApiError, formatApiErrorForOperator, parkSmartApi } from "@/lib/api";
import {
  formatActorType,
  formatEventType,
  formatParkingLocation,
  formatSlotStatus,
  formatWrongParkingReason,
  formatWrongParkingReportStatus,
} from "@/lib/parking-display";
import { subscribeToWrongParkingReportUpdates } from "@/lib/report-updates";
import type {
  ParkingEvent,
  SlotStatus,
  WrongParkingReport,
  WrongParkingReportStatus,
  ZoneId,
} from "@/lib/types";

const ZONES: ZoneId[] = ["A", "B", "C", "D"];
const REPORT_REFRESH_INTERVAL_MS = 3_000;
type MutationName = "park" | "leave" | "reset" | "scenario";
type FilterValue<T extends string> = T | "ALL";

function formatUpdatedAt(value: string | null) {
  if (!value) return "Chưa có dữ liệu";
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(value));
}

export function AdminDashboard() {
  const data = useParkSmartData();
  const [zoneFilter, setZoneFilter] = useState<FilterValue<ZoneId>>("ALL");
  const [statusFilter, setStatusFilter] =
    useState<FilterValue<SlotStatus>>("ALL");
  const [evFilter, setEvFilter] = useState<"ALL" | "EV" | "NO_EV">("ALL");
  const [parkSlotId, setParkSlotId] = useState("");
  const [parkVehicleId, setParkVehicleId] = useState("SIM-CAR-01");
  const [leaveSlotId, setLeaveSlotId] = useState("");
  const [events, setEvents] = useState<ParkingEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(true);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [reports, setReports] = useState<WrongParkingReport[]>([]);
  const [openReports, setOpenReports] = useState<WrongParkingReport[]>([]);
  const [reportFilter, setReportFilter] =
    useState<FilterValue<WrongParkingReportStatus>>("OPEN");
  const [reportsLoading, setReportsLoading] = useState(true);
  const [reportsError, setReportsError] = useState<string | null>(null);
  const [reportsLastUpdatedAt, setReportsLastUpdatedAt] = useState<Date | null>(null);
  const [mutationPending, setMutationPending] = useState<MutationName | null>(null);
  const [operationNotice, setOperationNotice] = useState<string | null>(null);
  const [selectedReportSlotId, setSelectedReportSlotId] = useState<string | null>(null);
  const [drawerReports, setDrawerReports] = useState<WrongParkingReport[]>([]);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [drawerError, setDrawerError] = useState<string | null>(null);
  const [pendingReportMutation, setPendingReportMutation] =
    useState<PendingReportMutation | null>(null);
  const [newReportNotice, setNewReportNotice] =
    useState<WrongParkingReport | null>(null);
  const mutationLockRef = useRef(false);
  const reportMutationLockRef = useRef(false);
  const observedReportIdsRef = useRef<Set<string> | null>(null);

  const loadEvents = useCallback(async (signal?: AbortSignal) => {
    setEventsLoading(true);
    setEventsError(null);
    try {
      const result = await parkSmartApi.getAdminEvents({ limit: 20 }, signal);
      if (!signal?.aborted) setEvents(result);
    } catch (error) {
      if (!signal?.aborted) {
        setEventsError(
          formatApiErrorForOperator(error, "Không thể tải lịch sử hoạt động."),
        );
      }
    } finally {
      if (!signal?.aborted) setEventsLoading(false);
    }
  }, []);

  const loadReports = useCallback(async (
    signal?: AbortSignal,
    showLoading = true,
  ) => {
    if (showLoading) setReportsLoading(true);
    setReportsError(null);
    try {
      const openRequest = parkSmartApi.getAdminReports(
        { status: "OPEN", limit: 100 },
        signal,
      );
      const visibleRequest =
        reportFilter === "OPEN"
          ? openRequest
          : parkSmartApi.getAdminReports(
              {
                status: reportFilter === "ALL" ? undefined : reportFilter,
                limit: 100,
              },
              signal,
            );
      const [openResult, visibleResult] = await Promise.all([
        openRequest,
        visibleRequest,
      ]);
      if (!signal?.aborted) {
        const nextIds = new Set(openResult.map((report) => report.id));
        if (observedReportIdsRef.current === null) {
          observedReportIdsRef.current = nextIds;
        } else {
          const newReport = openResult.find(
            (report) => !observedReportIdsRef.current?.has(report.id),
          );
          observedReportIdsRef.current = new Set([
            ...observedReportIdsRef.current,
            ...nextIds,
          ]);
          if (newReport) setNewReportNotice(newReport);
        }
        setOpenReports(openResult);
        setReports(visibleResult);
        setReportsLastUpdatedAt(new Date());
      }
    } catch (error) {
      if (!signal?.aborted) {
        setReportsError(
          formatApiErrorForOperator(error, "Không thể tải báo cáo của người dùng."),
        );
      }
    } finally {
      if (!signal?.aborted && showLoading) setReportsLoading(false);
    }
  }, [reportFilter]);

  useEffect(() => {
    const controller = new AbortController();
    void parkSmartApi
      .getAdminEvents({ limit: 20 }, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setEvents(result);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setEventsError(
            formatApiErrorForOperator(error, "Không thể tải lịch sử hoạt động."),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setEventsLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => void loadReports(controller.signal), 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [loadReports]);

  useEffect(() => {
    const controller = new AbortController();
    let requestPending = false;

    const refreshReportsInBackground = async () => {
      if (
        requestPending ||
        controller.signal.aborted ||
        document.visibilityState !== "visible"
      ) {
        return;
      }
      requestPending = true;
      try {
        await loadReports(controller.signal, false);
      } catch (error) {
        if (!controller.signal.aborted) {
          setReportsError(
            formatApiErrorForOperator(
              error,
              "Tạm thời không thể tự động cập nhật báo cáo.",
            ),
          );
        }
      } finally {
        requestPending = false;
      }
    };

    const intervalId = window.setInterval(
      () => void refreshReportsInBackground(),
      REPORT_REFRESH_INTERVAL_MS,
    );
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void refreshReportsInBackground();
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    const unsubscribe = subscribeToWrongParkingReportUpdates(() => {
      void refreshReportsInBackground();
    });

    return () => {
      controller.abort();
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      unsubscribe();
    };
  }, [loadReports]);

  const availableSlots = useMemo(
    () => data.slots.filter((slot) => slot.status === "AVAILABLE"),
    [data.slots],
  );
  const occupiedSlots = useMemo(
    () => data.slots.filter((slot) => slot.status === "OCCUPIED"),
    [data.slots],
  );

  const effectiveParkSlotId = availableSlots.some((slot) => slot.id === parkSlotId)
    ? parkSlotId
    : availableSlots[0]?.id ?? "";
  const effectiveLeaveSlotId = occupiedSlots.some((slot) => slot.id === leaveSlotId)
    ? leaveSlotId
    : occupiedSlots[0]?.id ?? "";

  const filteredSlots = useMemo(
    () =>
      data.slots.filter((slot) => {
        if (zoneFilter !== "ALL" && slot.zone_id !== zoneFilter) return false;
        if (statusFilter !== "ALL" && slot.status !== statusFilter) return false;
        if (evFilter === "EV" && !slot.has_charger) return false;
        if (evFilter === "NO_EV" && slot.has_charger) return false;
        return true;
      }),
    [data.slots, evFilter, statusFilter, zoneFilter],
  );
  const openReportCountBySlot = useMemo(
    () =>
      openReports.reduce<Record<string, number>>((counts, report) => {
        counts[report.slot_id] = (counts[report.slot_id] ?? 0) + 1;
        return counts;
      }, {}),
    [openReports],
  );
  const selectedReportedSlot =
    data.slots.find((slot) => slot.id === selectedReportSlotId) ?? null;

  const utilization = data.status?.total
    ? Math.round(
        ((data.status.reserved + data.status.occupied) / data.status.total) * 100,
      )
    : 0;
  const availableEv = data.slots.filter(
    (slot) => slot.has_charger && slot.status === "AVAILABLE",
  ).length;
  const leaveSlot =
    occupiedSlots.find((slot) => slot.id === effectiveLeaveSlotId) ?? null;
  const operationDisabled = mutationPending !== null;

  async function loadDrawerReports(slotId = selectedReportSlotId) {
    if (!slotId) return;
    setDrawerLoading(true);
    setDrawerError(null);
    try {
      const result = await parkSmartApi.getAdminReports({
        slotId,
        limit: 100,
      });
      setDrawerReports(result);
    } catch (error) {
      setDrawerError(
        formatApiErrorForOperator(error, "Không thể tải chi tiết báo cáo."),
      );
    } finally {
      setDrawerLoading(false);
    }
  }

  function openReportedSlot(slotId: string) {
    setSelectedReportSlotId(slotId);
    setDrawerReports([]);
    setDrawerError(null);
    void loadDrawerReports(slotId);
  }

  async function mutateReport(
    report: WrongParkingReport,
    action: ReportMutationAction,
    mutation: () => Promise<unknown>,
  ): Promise<boolean> {
    if (reportMutationLockRef.current) return false;
    reportMutationLockRef.current = true;
    setPendingReportMutation({ reportId: report.id, action });
    setDrawerError(null);
    try {
      await mutation();
      await Promise.all([
        loadReports(undefined, false),
        loadDrawerReports(report.slot_id),
      ]);
      setOperationNotice(
        action === "resolve"
          ? `Đã resolve report ${report.id}.`
          : action === "confirm"
            ? `Da confirm report ${report.id}.`
            : action === "reject"
              ? `Da reject report ${report.id}.`
              : action === "reopen"
                ? `Đã reopen report ${report.id}.`
                : `Đã xóa vĩnh viễn report ${report.id}.`,
      );
      return true;
    } catch (error) {
      if (error instanceof ApiError && error.code === "REPORT_VERSION_CONFLICT") {
        try {
          const latest = await parkSmartApi.getAdminReport(report.id);
          setDrawerReports((current) => [
            latest,
            ...current.filter((candidate) => candidate.id !== latest.id),
          ]);
          await loadReports(undefined, false);
        } catch {
          await Promise.all([
            loadReports(undefined, false),
            loadDrawerReports(report.slot_id),
          ]);
        }
        setDrawerError(
          "Report đã thay đổi trên server. Dữ liệu mới nhất đã được tải lại; hãy kiểm tra trước khi thao tác tiếp.",
        );
      } else {
        setDrawerError(
          formatApiErrorForOperator(error, "Không thể cập nhật report."),
        );
      }
      return false;
    } finally {
      reportMutationLockRef.current = false;
      setPendingReportMutation(null);
    }
  }

  function resolveReport(
    report: WrongParkingReport,
    resolutionNote: string | null,
  ) {
    return mutateReport(report, "resolve", () =>
      parkSmartApi.resolveAdminReport(report.id, {
        status: "RESOLVED",
        resolution_note: resolutionNote,
        expected_version: report.version,
      }),
    );
  }

  function reopenReport(report: WrongParkingReport) {
    return mutateReport(report, "reopen", () =>
      parkSmartApi.reopenAdminReport(report.id, {
        expected_version: report.version,
      }),
    );
  }

  function deleteReport(report: WrongParkingReport) {
    return mutateReport(report, "delete", () =>
      parkSmartApi.deleteAdminReport(report.id, {
        expected_version: report.version,
      }),
    );
  }

  function confirmReport(report: WrongParkingReport, reviewNote: string | null) {
    return mutateReport(report, "confirm", () =>
      parkSmartApi.confirmAdminReport(report.id, {
        review_note: reviewNote,
        expected_version: report.version,
      }),
    );
  }

  function rejectReport(report: WrongParkingReport, reviewNote: string | null) {
    return mutateReport(report, "reject", () =>
      parkSmartApi.rejectAdminReport(report.id, {
        review_note: reviewNote,
        expected_version: report.version,
      }),
    );
  }

  async function loadReportEvidence(report: WrongParkingReport) {
    try {
      const result = await parkSmartApi.getAdminReportEvidenceUrl(report.id);
      return result.signed_url;
    } catch (error) {
      setDrawerError(
        formatApiErrorForOperator(error, "Khong the tai anh bang chung."),
      );
      return null;
    }
  }

  async function runMutation(
    name: MutationName,
    action: () => Promise<unknown>,
    successMessage: string,
  ) {
    if (mutationLockRef.current) return;
    mutationLockRef.current = true;
    setMutationPending(name);
    setOperationNotice(null);
    try {
      await action();
      await data.refresh();
      await loadEvents();
      setOperationNotice(successMessage);
    } catch (error) {
      setOperationNotice(
        formatApiErrorForOperator(error, "Không thể hoàn tất thao tác vận hành."),
      );
    } finally {
      mutationLockRef.current = false;
      setMutationPending(null);
    }
  }

  function submitPark(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!effectiveParkSlotId || !/^SIM-CAR-[0-9]{2,}$/.test(parkVehicleId)) return;
    void runMutation(
      "park",
      () =>
        parkSmartApi.parkSimulatedVehicle({
          slot_id: effectiveParkSlotId,
          vehicle_id: parkVehicleId,
        }),
      `Đã ghi nhận ${parkVehicleId} đỗ tại ${formatParkingLocation(effectiveParkSlotId)}.`,
    );
  }

  function submitLeave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!leaveSlot?.occupied_by_vehicle_id) return;
    void runMutation(
      "leave",
      () =>
        parkSmartApi.leaveSimulatedVehicle({
          slot_id: leaveSlot.id,
          vehicle_id: leaveSlot.occupied_by_vehicle_id as string,
        }),
      `Đã ghi nhận xe rời ${formatParkingLocation(leaveSlot.id)}.`,
    );
  }

  async function retryDashboard() {
    setOperationNotice(null);
    await Promise.allSettled([data.refresh(), loadEvents(), loadReports()]);
  }

  return (
    <main className="admin-shell">
      <header className="admin-topbar">
        <div>
          <p className="eyebrow green">TRUNG TÂM VẬN HÀNH</p>
          <h1>Bảng điều khiển vận hành</h1>
          <p>Quản trị viên thử nghiệm · các thao tác mô phỏng chỉ hoạt động trong chế độ thử nghiệm</p>
        </div>
        <div className="admin-top-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={() => void retryDashboard()}
            disabled={data.refreshing || eventsLoading}
          >
            {data.refreshing ? "Đang làm mới…" : "Làm mới dữ liệu"}
          </button>
          <Link href="/">← Về giao diện người dùng</Link>
        </div>
      </header>

      {(data.error || eventsError || reportsError) && !data.loading && (
        <div className="admin-error" role="alert">
          <span>
            {data.error
              ? formatApiErrorForOperator(data.error, "Không thể tải dữ liệu bãi xe.")
              : eventsError ?? reportsError}
          </span>
          <button type="button" onClick={() => void retryDashboard()}>Thử lại</button>
        </div>
      )}

      {operationNotice && (
        <div className="admin-operation-notice" role="status" aria-live="polite">
          {operationNotice}
        </div>
      )}

      {newReportNotice && (
        <button
          type="button"
          className="admin-operation-notice"
          onClick={() => {
            openReportedSlot(newReportNotice.slot_id);
            setNewReportNotice(null);
          }}
        >
          New report at {formatParkingLocation(newReportNotice.slot_id)}
        </button>
      )}

      {data.loading && (
        <section className="card admin-loading" aria-live="polite">
          Đang tải dữ liệu vận hành…
        </section>
      )}

      {!data.loading && data.status && (
        <>
          <section className="admin-metrics" aria-label="Chỉ số bãi xe">
            <article><small>Tổng số ô</small><b>{data.status.total}</b></article>
            <article><small>Ô đang trống</small><b>{data.status.available}</b></article>
            <article><small>Ô đã giữ</small><b>{data.status.reserved}</b></article>
            <article><small>Ô đã có xe</small><b>{data.status.occupied}</b></article>
            <article><small>Tỷ lệ sử dụng</small><b>{utilization}%</b></article>
            <article><small>Ô sạc điện đang trống</small><b>{availableEv}</b></article>
            <article className="last-updated"><small>Cập nhật gần nhất</small><b>{formatUpdatedAt(data.lastUpdatedAt)}</b></article>
          </section>

          <section className="card zone-density-card">
            <div className="admin-section-heading">
              <div><p className="eyebrow green">MẬT ĐỘ THEO KHU</p><h2>Khu A–D</h2></div>
              <span>Tính trực tiếp từ trạng thái hiện tại</span>
            </div>
            <div className="zone-density-grid">
              {ZONES.map((zoneId) => {
                const zone = data.status?.by_zone[zoneId];
                const total = zone
                  ? zone.AVAILABLE + zone.RESERVED + zone.OCCUPIED
                  : 0;
                const used = zone ? zone.RESERVED + zone.OCCUPIED : 0;
                const density = total ? Math.round((used / total) * 100) : 0;
                return (
                  <article key={zoneId}>
                    <div><b>Khu {zoneId}</b><strong>{density}%</strong></div>
                    <div className="density-track" aria-label={`Mật độ khu ${zoneId}: ${density}%`}><i style={{ width: `${density}%` }} /></div>
                    <small>{used}/{total} ô đang được sử dụng</small>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="admin-main-grid">
            <div className="admin-map-column">
              <section className="card admin-filters" aria-label="Bộ lọc bản đồ">
                <label>Khu
                  <select value={zoneFilter} onChange={(event) => setZoneFilter(event.target.value as FilterValue<ZoneId>)}>
                    <option value="ALL">Tất cả khu</option>
                    {ZONES.map((zone) => <option key={zone} value={zone}>Khu {zone}</option>)}
                  </select>
                </label>
                <label>Trạng thái
                  <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as FilterValue<SlotStatus>)}>
                    <option value="ALL">Tất cả trạng thái</option>
                    <option value="AVAILABLE">Đang trống</option>
                    <option value="RESERVED">Đã giữ</option>
                    <option value="OCCUPIED">Đã có xe</option>
                  </select>
                </label>
                <label>Sạc điện
                  <select value={evFilter} onChange={(event) => setEvFilter(event.target.value as "ALL" | "EV" | "NO_EV")}>
                    <option value="ALL">Tất cả</option>
                    <option value="EV">Có sạc điện</option>
                    <option value="NO_EV">Không có sạc điện</option>
                  </select>
                </label>
                <span>{filteredSlots.length} ô phù hợp</span>
              </section>
              {data.map && (
                <ParkingMap
                  map={data.map}
                  slots={filteredSlots}
                  status={data.status}
                  heading="Bản đồ vận hành tầng F1"
                  description="Lọc theo khu, trạng thái hoặc khả năng sạc điện"
                  showSummary={false}
                  openReportCountBySlot={openReportCountBySlot}
                  onOpenReportedSlot={openReportedSlot}
                />
              )}
              {filteredSlots.length === 0 && (
                <div className="admin-empty" role="status">Không có ô nào phù hợp với bộ lọc hiện tại.</div>
              )}
            </div>

            <aside className="admin-operations card">
              <div className="admin-section-heading">
                <div><p className="eyebrow green">MÔ PHỎNG BÃI XE</p><h2>Điều khiển thủ công</h2></div>
              </div>
              <form onSubmit={submitPark}>
                <h3>Ghi nhận xe đỗ</h3>
                <label>Ô đang trống
                  <select value={effectiveParkSlotId} onChange={(event) => setParkSlotId(event.target.value)} disabled={operationDisabled || availableSlots.length === 0}>
                    {availableSlots.map((slot) => <option key={slot.id} value={slot.id}>{formatParkingLocation(slot.id)}</option>)}
                  </select>
                </label>
                <label>Mã xe mô phỏng
                  <input value={parkVehicleId} onChange={(event) => setParkVehicleId(event.target.value.toUpperCase())} pattern="SIM-CAR-[0-9]{2,}" placeholder="SIM-CAR-01" disabled={operationDisabled} />
                </label>
                <button className="primary-button" disabled={operationDisabled || !effectiveParkSlotId || !/^SIM-CAR-[0-9]{2,}$/.test(parkVehicleId)}>
                  {mutationPending === "park" ? "Đang xử lý…" : "Ghi nhận xe đỗ"}
                </button>
              </form>

              <form onSubmit={submitLeave}>
                <h3>Ghi nhận xe rời ô</h3>
                <label>Ô đang có xe
                  <select value={effectiveLeaveSlotId} onChange={(event) => setLeaveSlotId(event.target.value)} disabled={operationDisabled || occupiedSlots.length === 0}>
                    {occupiedSlots.map((slot) => <option key={slot.id} value={slot.id}>{formatParkingLocation(slot.id)} · {slot.occupied_by_vehicle_id}</option>)}
                  </select>
                </label>
                <button className="secondary-button" disabled={operationDisabled || !leaveSlot?.occupied_by_vehicle_id}>
                  {mutationPending === "leave" ? "Đang xử lý…" : "Ghi nhận xe rời ô"}
                </button>
              </form>

              <div className="admin-scenario-actions">
                <button type="button" className="secondary-button" disabled={operationDisabled} onClick={() => void runMutation("reset", () => parkSmartApi.resetDemo(), "Đã đưa dữ liệu thử nghiệm về trạng thái ban đầu.")}>
                  {mutationPending === "reset" ? "Đang đặt lại…" : "Đặt lại dữ liệu thử nghiệm"}
                </button>
                <button type="button" className="primary-button" disabled={operationDisabled} onClick={() => void runMutation("scenario", () => parkSmartApi.runFixedScenario(), "Đã chạy xong kịch bản cố định.")}>
                  {mutationPending === "scenario" ? "Đang chạy…" : "Chạy kịch bản cố định"}
                </button>
              </div>
            </aside>
          </section>

          <section className="card admin-events">
            <div className="admin-section-heading">
              <div><p className="eyebrow green">PHẢN ÁNH TỪ NGƯỜI DÙNG</p><h2>Báo cáo xe đỗ sai vị trí</h2></div>
              <div className="admin-report-refresh">
                <label>
                  Trạng thái report
                  <select
                    value={reportFilter}
                    onChange={(event) =>
                      setReportFilter(
                        event.target.value as FilterValue<WrongParkingReportStatus>,
                      )
                    }
                  >
                    <option value="OPEN">Đang mở</option>
                    <option value="RESOLVED">Đã xử lý</option>
                    <option value="ALL">Tất cả</option>
                  </select>
                </label>
                <span aria-live="polite">
                  Tự động cập nhật
                  {reportsLastUpdatedAt
                    ? ` · ${reportsLastUpdatedAt.toLocaleTimeString("vi-VN")}`
                    : ""}
                </span>
                <button type="button" onClick={() => void loadReports()} disabled={reportsLoading}>{reportsLoading ? "Đang tải…" : "Tải lại"}</button>
              </div>
            </div>
            {reportsLoading && <p className="admin-empty" role="status">Đang tải báo cáo…</p>}
            {!reportsLoading && reportsError && <div className="admin-error" role="alert"><span>{reportsError}</span><button type="button" onClick={() => void loadReports()}>Thử lại</button></div>}
            {!reportsLoading && !reportsError && reports.length === 0 && <p className="admin-empty">Chưa có báo cáo xe đỗ sai vị trí.</p>}
            {!reportsLoading && !reportsError && reports.length > 0 && (
              <div className="admin-report-list">
                {reports.map((report) => (
                  <button
                    type="button"
                    key={report.id}
                    className="admin-report-row"
                    onClick={() => openReportedSlot(report.slot_id)}
                  >
                    <div>
                      <b>{formatParkingLocation(report.slot_id)}</b>
                      <small>{formatWrongParkingReason(report.reason_code)}</small>
                    </div>
                    <p>{report.description ?? "Không có mô tả bổ sung"}</p>
                    <span className={`report-status status-${report.status.toLowerCase()}`}>
                      {formatWrongParkingReportStatus(report.status)}
                    </span>
                    <time dateTime={report.created_at}>{formatUpdatedAt(report.created_at)}</time>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="card admin-events">
            <div className="admin-section-heading">
              <div><p className="eyebrow green">NHẬT KÝ GẦN ĐÂY</p><h2>Sự kiện đỗ xe gần đây</h2></div>
              <button type="button" onClick={() => void loadEvents()} disabled={eventsLoading}>{eventsLoading ? "Đang tải…" : "Tải lại"}</button>
            </div>
            {eventsLoading && <p className="admin-empty" role="status">Đang tải lịch sử hoạt động…</p>}
            {!eventsLoading && eventsError && <div className="admin-error" role="alert"><span>{eventsError}</span><button type="button" onClick={() => void loadEvents()}>Thử lại</button></div>}
            {!eventsLoading && !eventsError && events.length === 0 && <p className="admin-empty">Chưa có sự kiện đỗ xe nào.</p>}
            {!eventsLoading && !eventsError && events.length > 0 && (
              <div className="admin-event-list">
                {events.map((event) => (
                  <article key={event.id}>
                    <span className={`event-status ${event.new_status?.toLowerCase() ?? "neutral"}`} aria-hidden="true" />
                    <div><b>{formatEventType(event.event_type)}</b><small>{event.slot_id ? formatParkingLocation(event.slot_id) : "Toàn bãi"}</small></div>
                    <div><span>{event.old_status ? formatSlotStatus(event.old_status) : "—"} → {event.new_status ? formatSlotStatus(event.new_status) : "—"}</span><small>{formatActorType(event.actor_type)}{event.actor_id ? ` · ${event.actor_id}` : ""}</small></div>
                    <time dateTime={event.created_at}>{formatUpdatedAt(event.created_at)}</time>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      )}
      {selectedReportSlotId && (
        <ReportDetailDrawer
          slot={selectedReportedSlot}
          reports={drawerReports}
          loading={drawerLoading}
          error={drawerError}
          pendingMutation={pendingReportMutation}
          onClose={() => {
            if (!pendingReportMutation) setSelectedReportSlotId(null);
          }}
          onRefresh={() => loadDrawerReports(selectedReportSlotId)}
          onResolve={resolveReport}
          onReopen={reopenReport}
          onDelete={deleteReport}
          onConfirm={confirmReport}
          onReject={rejectReport}
          onLoadEvidence={loadReportEvidence}
        />
      )}
    </main>
  );
}
