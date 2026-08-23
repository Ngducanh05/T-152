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
  WrongParkingReportVerificationOutcome,
  SlotObservation,
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
  const [observations, setObservations] = useState<SlotObservation[]>([]);
  const [observationsLoading, setObservationsLoading] = useState(true);
  const [observationsError, setObservationsError] = useState<string | null>(null);
  const [selectedObservationId, setSelectedObservationId] = useState<string | null>(null);
  const [observationRejectReason, setObservationRejectReason] = useState("");
  const [observationMutationPending, setObservationMutationPending] = useState(false);
  const [mutationPending, setMutationPending] = useState<MutationName | null>(null);
  const [operationNotice, setOperationNotice] = useState<string | null>(null);
  const [selectedReportSlotId, setSelectedReportSlotId] = useState<string | null>(null);
  const [selectedAdminSlotId, setSelectedAdminSlotId] = useState<string | null>(null);
  const [selectedSlotStatus, setSelectedSlotStatus] =
    useState<Exclude<SlotStatus, "RESERVED">>("AVAILABLE");
  const [slotStatusMutationPending, setSlotStatusMutationPending] = useState(false);
  const [drawerReports, setDrawerReports] = useState<WrongParkingReport[]>([]);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [drawerError, setDrawerError] = useState<string | null>(null);
  const [pendingReportMutation, setPendingReportMutation] =
    useState<PendingReportMutation | null>(null);
  const mutationLockRef = useRef(false);
  const reportMutationLockRef = useRef(false);

  const loadObservations = useCallback(async (
    signal?: AbortSignal,
    showLoading = true,
  ) => {
    if (showLoading) setObservationsLoading(true);
    setObservationsError(null);
    try {
      const result = await parkSmartApi.getAdminObservations(
        { status: "PENDING", limit: 100 },
        signal,
      );
      if (!signal?.aborted) setObservations(result);
    } catch (error) {
      if (!signal?.aborted) {
        setObservationsError(
          formatApiErrorForOperator(error, "Không thể tải quan sát chờ xác minh."),
        );
      }
    } finally {
      if (!signal?.aborted && showLoading) setObservationsLoading(false);
    }
  }, []);

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
    const timer = window.setTimeout(
      () => void Promise.all([
        loadReports(controller.signal),
        loadObservations(controller.signal),
      ]),
      0,
    );
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [loadObservations, loadReports]);

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
        await Promise.all([
          loadReports(controller.signal, false),
          loadObservations(controller.signal, false),
        ]);
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
  }, [loadObservations, loadReports]);

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
  const pendingObservationCountBySlot = useMemo(
    () =>
      observations.reduce<Record<string, number>>((counts, observation) => {
        counts[observation.slot_id] = (counts[observation.slot_id] ?? 0) + 1;
        return counts;
      }, {}),
    [observations],
  );
  const selectedObservation =
    observations.find((observation) => observation.id === selectedObservationId) ?? null;
  const selectedReportedSlot =
    data.slots.find((slot) => slot.id === selectedReportSlotId) ?? null;
  const selectedAdminSlot =
    data.slots.find((slot) => slot.id === selectedAdminSlotId) ?? null;

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
    const slot = data.slots.find((candidate) => candidate.id === slotId);
    setZoneFilter("ALL");
    setStatusFilter("ALL");
    setEvFilter("ALL");
    setSelectedAdminSlotId(slotId);
    setSelectedSlotStatus(slot?.status === "OCCUPIED" ? "OCCUPIED" : "AVAILABLE");
    setSelectedReportSlotId(slotId);
    setDrawerReports([]);
    setDrawerError(null);
    void loadDrawerReports(slotId);
  }

  function selectObservation(observation: SlotObservation) {
    const slot = data.slots.find((candidate) => candidate.id === observation.slot_id);
    setZoneFilter("ALL");
    setStatusFilter("ALL");
    setEvFilter("ALL");
    setSelectedReportSlotId(null);
    setSelectedAdminSlotId(observation.slot_id);
    setSelectedSlotStatus(slot?.status === "OCCUPIED" ? "OCCUPIED" : "AVAILABLE");
    setSelectedObservationId(observation.id);
    setObservationRejectReason("");
  }

  function openObservedSlot(slotId: string) {
    const observation = observations.find((item) => item.slot_id === slotId);
    if (observation) selectObservation(observation);
  }

  function inspectSlot(slotId: string) {
    const slot = data.slots.find((candidate) => candidate.id === slotId);
    setZoneFilter("ALL");
    setStatusFilter("ALL");
    setEvFilter("ALL");
    setSelectedAdminSlotId(slotId);
    setSelectedSlotStatus(slot?.status === "OCCUPIED" ? "OCCUPIED" : "AVAILABLE");
    setSelectedObservationId(null);
    setSelectedReportSlotId(null);
  }

  async function updateSelectedSlotStatus() {
    if (!selectedAdminSlot || slotStatusMutationPending) return;
    setSlotStatusMutationPending(true);
    setOperationNotice(null);
    try {
      await parkSmartApi.updateAdminSlotStatus(selectedAdminSlot.id, {
        status: selectedSlotStatus,
        expected_version: selectedAdminSlot.version,
      });
      await Promise.all([
        data.refresh(),
        loadEvents(),
        loadReports(undefined, false),
        loadObservations(undefined, false),
      ]);
      setOperationNotice(
        `Đã cập nhật ${formatParkingLocation(selectedAdminSlot.id)} thành ${formatSlotStatus(selectedSlotStatus)}.`,
      );
    } catch (error) {
      await Promise.all([data.refresh(), loadEvents()]);
      setOperationNotice(
        formatApiErrorForOperator(error, "Không thể cập nhật trạng thái ô đỗ."),
      );
    } finally {
      setSlotStatusMutationPending(false);
    }
  }

  async function mutateObservation(action: "verify" | "reject") {
    if (!selectedObservation || observationMutationPending) return;
    setObservationMutationPending(true);
    setObservationsError(null);
    try {
      if (action === "verify") {
        await parkSmartApi.verifyAdminObservation(selectedObservation.id, {
          expected_version: selectedObservation.version,
        });
      } else {
        await parkSmartApi.rejectAdminObservation(selectedObservation.id, {
          expected_version: selectedObservation.version,
          reason: observationRejectReason.trim() || null,
        });
      }
      setSelectedObservationId(null);
      await Promise.all([
        loadObservations(undefined, false),
        loadReports(undefined, false),
        loadEvents(),
        data.refresh(),
      ]);
      setOperationNotice(
        action === "verify" ? "Đã xác minh đóng góp." : "Đã từ chối đóng góp.",
      );
    } catch (error) {
      await Promise.all([loadObservations(undefined, false), data.refresh()]);
      setObservationsError(
        error instanceof ApiError && error.code === "OBSERVATION_VERSION_CONFLICT"
          ? "Quan sát đã thay đổi trên server. Dữ liệu mới nhất đã được tải lại."
          : formatApiErrorForOperator(error, "Không thể xử lý quan sát."),
      );
    } finally {
      setObservationMutationPending(false);
    }
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
        loadObservations(undefined, false),
        loadEvents(),
        data.refresh(),
      ]);
      setOperationNotice(
        action === "resolve"
          ? `Đã resolve report ${report.id}.`
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
    outcome: Exclude<WrongParkingReportVerificationOutcome, "PENDING">,
    resolutionNote: string | null,
  ) {
    return mutateReport(report, "resolve", () =>
      parkSmartApi.resolveAdminReport(report.id, {
        status: "RESOLVED",
        verification_outcome: outcome,
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
                  heading="Bản đồ vận hành nhiều tầng"
                  description="Lọc theo khu, trạng thái hoặc khả năng sạc điện"
                  showSummary={false}
                  openReportCountBySlot={openReportCountBySlot}
                  pendingObservationCountBySlot={pendingObservationCountBySlot}
                  selectedSlotId={selectedAdminSlotId ?? selectedObservation?.slot_id ?? null}
                  onSelectSlot={inspectSlot}
                  onOpenReportedSlot={openReportedSlot}
                  onOpenObservedSlot={openObservedSlot}
                />
              )}
              {selectedAdminSlot && (
                <aside className="card admin-slot-detail" aria-labelledby="admin-slot-detail-title">
                  <header>
                    <div>
                      <p className="eyebrow green">CHI TIẾT Ô ĐỖ</p>
                      <h2 id="admin-slot-detail-title">{formatParkingLocation(selectedAdminSlot.id)}</h2>
                    </div>
                    <button
                      type="button"
                      className="modal-close"
                      aria-label="Đóng chi tiết ô đỗ"
                      onClick={() => {
                        setSelectedAdminSlotId(null);
                        setSelectedObservationId(null);
                        setSelectedReportSlotId(null);
                      }}
                    >×</button>
                  </header>
                  <dl>
                    <div><dt>Trạng thái</dt><dd>{formatSlotStatus(selectedAdminSlot.status)}</dd></div>
                    <div><dt>Phiên bản</dt><dd>{selectedAdminSlot.version}</dd></div>
                    <div><dt>Xe đang ghi nhận</dt><dd>{selectedAdminSlot.occupied_by_vehicle_id ?? "Không có"}</dd></div>
                    <div><dt>Report đang mở</dt><dd>{openReportCountBySlot[selectedAdminSlot.id] ?? 0}</dd></div>
                    <div><dt>Quan sát chờ xác minh</dt><dd>{pendingObservationCountBySlot[selectedAdminSlot.id] ?? 0}</dd></div>
                  </dl>
                  <div className="admin-slot-issue-actions">
                    {(openReportCountBySlot[selectedAdminSlot.id] ?? 0) > 0 && (
                      <button type="button" className="secondary-button" onClick={() => openReportedSlot(selectedAdminSlot.id)}>
                        Xem report của ô này
                      </button>
                    )}
                    {(pendingObservationCountBySlot[selectedAdminSlot.id] ?? 0) > 0 && (
                      <button type="button" className="secondary-button" onClick={() => openObservedSlot(selectedAdminSlot.id)}>
                        Xem quan sát chờ xác minh
                      </button>
                    )}
                  </div>
                  <div className="admin-slot-status-control">
                    <label>
                      Cập nhật trạng thái
                      <select
                        value={selectedSlotStatus}
                        disabled={slotStatusMutationPending || selectedAdminSlot.status === "RESERVED"}
                        onChange={(event) => setSelectedSlotStatus(event.target.value as Exclude<SlotStatus, "RESERVED">)}
                      >
                        <option value="AVAILABLE">Đang trống</option>
                        <option value="OCCUPIED">Đã có xe</option>
                      </select>
                    </label>
                    <button
                      type="button"
                      className="primary-button"
                      disabled={
                        slotStatusMutationPending ||
                        selectedAdminSlot.status === "RESERVED" ||
                        selectedAdminSlot.status === selectedSlotStatus
                      }
                      onClick={() => void updateSelectedSlotStatus()}
                    >
                      {slotStatusMutationPending ? "Đang cập nhật…" : "Lưu trạng thái"}
                    </button>
                  </div>
                  {selectedAdminSlot.status === "RESERVED" && (
                    <p className="admin-slot-guard" role="note">
                      Ô đang được giữ chỗ. Hãy xử lý reservation trước khi thay đổi trạng thái.
                    </p>
                  )}
                </aside>
              )}
              {selectedObservation && (
                <aside className="card observation-detail-panel" aria-labelledby="observation-detail-title">
                  <header>
                    <div>
                      <p className="eyebrow green">CHI TIẾT QUAN SÁT</p>
                      <h2 id="observation-detail-title">
                        {formatParkingLocation(selectedObservation.slot_id)}
                      </h2>
                    </div>
                    <button
                      type="button"
                      className="modal-close"
                      aria-label="Đóng chi tiết quan sát"
                      disabled={observationMutationPending}
                      onClick={() => setSelectedObservationId(null)}
                    >×</button>
                  </header>
                  <dl>
                    <div><dt>Người gửi</dt><dd>Người dùng …{selectedObservation.observer_user_id.slice(-4)}</dd></div>
                    <div><dt>Tầng / khu / ô</dt><dd>{formatParkingLocation(selectedObservation.slot_id)}</dd></div>
                    <div><dt>Quan sát</dt><dd>{formatSlotStatus(selectedObservation.observed_status)}</dd></div>
                    <div><dt>Trạng thái hiện tại</dt><dd>{formatSlotStatus(data.slots.find((slot) => slot.id === selectedObservation.slot_id)?.status ?? "AVAILABLE")}</dd></div>
                    <div><dt>Được gửi</dt><dd>{formatUpdatedAt(selectedObservation.created_at)}</dd></div>
                    <div><dt>Hết hạn</dt><dd>{formatUpdatedAt(selectedObservation.expires_at)}</dd></div>
                    <div><dt>Điểm chờ</dt><dd>{selectedObservation.reward_points}</dd></div>
                  </dl>
                  <label>
                    Lý do từ chối (không bắt buộc)
                    <textarea
                      maxLength={500}
                      value={observationRejectReason}
                      disabled={observationMutationPending}
                      onChange={(event) => setObservationRejectReason(event.target.value)}
                    />
                  </label>
                  <div className="contribution-actions">
                    <button
                      type="button"
                      className="primary-button"
                      disabled={observationMutationPending}
                      onClick={() => void mutateObservation("verify")}
                    >{observationMutationPending ? "Đang xử lý…" : "Xác minh"}</button>
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={observationMutationPending}
                      onClick={() => void mutateObservation("reject")}
                    >Từ chối</button>
                  </div>
                </aside>
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

          <section className="card admin-events" aria-labelledby="pending-contributions-title">
            <div className="admin-section-heading">
              <div>
                <p className="eyebrow green">CỘNG ĐỒNG PARKSMART</p>
                <h2 id="pending-contributions-title">Đóng góp chờ xác minh</h2>
                <p>Quan sát ô bên cạnh</p>
              </div>
              <button type="button" onClick={() => void loadObservations()} disabled={observationsLoading}>
                {observationsLoading ? "Đang tải…" : "Tải lại"}
              </button>
            </div>
            {observationsError && <div className="admin-error" role="alert">{observationsError}</div>}
            {!observationsLoading && !observationsError && observations.length === 0 && (
              <p className="admin-empty">Không có quan sát nào đang chờ.</p>
            )}
            <div className="admin-report-list">
              {observations.map((observation) => (
                <button
                  type="button"
                  key={observation.id}
                  className="admin-report-row observation-row"
                  data-observation-id={observation.id}
                  onClick={() => selectObservation(observation)}
                >
                  <div>
                    <b>{formatParkingLocation(observation.slot_id)}</b>
                    <small>Người dùng …{observation.observer_user_id.slice(-4)}</small>
                  </div>
                  <p>Quan sát: {formatSlotStatus(observation.observed_status)}</p>
                  <span className="reward-pill">+{observation.reward_points} chờ</span>
                  <time dateTime={observation.created_at}>{formatUpdatedAt(observation.created_at)}</time>
                </button>
              ))}
            </div>
          </section>

          <section className="card admin-events">
            <div className="admin-section-heading">
              <div><p className="eyebrow green">ĐÓNG GÓP CHỜ XÁC MINH</p><h2>Report xe đỗ sai</h2></div>
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
        />
      )}
    </main>
  );
}
