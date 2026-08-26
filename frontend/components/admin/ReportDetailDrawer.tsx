"use client";

import Image from "next/image";
import { useMemo, useState } from "react";

import {
  formatParkingLocation,
  formatSlotStatus,
  formatVerificationOutcome,
  formatWrongParkingReason,
  formatWrongParkingReportStatus,
} from "@/lib/parking-display";
import type {
  ParkingSlot,
  WrongParkingReport,
  WrongParkingReportVerificationOutcome,
} from "@/lib/types";

export type ReportMutationAction = "resolve" | "reopen" | "delete";
export interface PendingReportMutation {
  reportId: string;
  action: ReportMutationAction;
}

interface ReportDetailDrawerProps {
  slot: ParkingSlot | null;
  reports: WrongParkingReport[];
  loading: boolean;
  error: string | null;
  pendingMutation: PendingReportMutation | null;
  onClose: () => void;
  onRefresh: () => Promise<void>;
  onResolve: (
    report: WrongParkingReport,
    outcome: Exclude<WrongParkingReportVerificationOutcome, "PENDING">,
    resolutionNote: string | null,
  ) => Promise<boolean>;
  onReopen: (report: WrongParkingReport) => Promise<boolean>;
  onDelete: (report: WrongParkingReport) => Promise<boolean>;
  onLoadEvidence: (report: WrongParkingReport) => Promise<string | null>;
}

function formatReportTime(value: string) {
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}

export function ReportDetailDrawer({
  slot,
  reports,
  loading,
  error,
  pendingMutation,
  onClose,
  onRefresh,
  onResolve,
  onReopen,
  onDelete,
  onLoadEvidence,
}: ReportDetailDrawerProps) {
  const [resolutionNotes, setResolutionNotes] = useState<Record<string, string>>({});
  const [resolutionOutcomes, setResolutionOutcomes] = useState<
    Record<string, Exclude<WrongParkingReportVerificationOutcome, "PENDING"> | "">
  >({});
  const [deleteCandidate, setDeleteCandidate] =
    useState<WrongParkingReport | null>(null);
  const [evidenceUrls, setEvidenceUrls] = useState<Record<string, string>>({});
  const [loadingEvidenceId, setLoadingEvidenceId] = useState<string | null>(null);
  const orderedReports = useMemo(
    () =>
      [...reports].toSorted(
        (left, right) =>
          new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
      ),
    [reports],
  );
  const anyMutationPending = pendingMutation !== null;

  async function confirmDelete() {
    if (!deleteCandidate || anyMutationPending) return;
    const deleted = await onDelete(deleteCandidate);
    if (deleted) setDeleteCandidate(null);
  }

  async function loadEvidence(report: WrongParkingReport) {
    if (loadingEvidenceId) return;
    setLoadingEvidenceId(report.id);
    try {
      const signedUrl = await onLoadEvidence(report);
      if (signedUrl) {
        setEvidenceUrls((current) => ({ ...current, [report.id]: signedUrl }));
      }
    } finally {
      setLoadingEvidenceId(null);
    }
  }

  return (
    <div className="admin-drawer-backdrop" onClick={() => !anyMutationPending && onClose()}>
      <aside
        className="report-detail-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="report-drawer-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <p className="eyebrow green">CHI TIẾT PHẢN ÁNH</p>
            <h2 id="report-drawer-title">
              {formatParkingLocation(slot?.id)}
            </h2>
            <p>
              Trạng thái ô thực tế: <b>{slot ? formatSlotStatus(slot.status) : "Không xác định"}</b>
            </p>
          </div>
          <button
            type="button"
            className="modal-close"
            aria-label="Đóng chi tiết báo cáo"
            onClick={onClose}
            disabled={anyMutationPending}
          >
            ×
          </button>
        </header>

        <div className="drawer-refresh-row">
          <span>{orderedReports.length} báo cáo tại ô này</span>
          <button type="button" onClick={() => void onRefresh()} disabled={loading || anyMutationPending}>
            {loading ? "Đang tải…" : "Tải lại"}
          </button>
        </div>

        {error && <div className="report-drawer-error" role="alert">{error}</div>}
        {loading && <p className="report-drawer-empty" role="status">Đang tải chi tiết báo cáo…</p>}
        {!loading && orderedReports.length === 0 && (
          <p className="report-drawer-empty">Không còn báo cáo tại ô này.</p>
        )}

        <div className="report-detail-list">
          {orderedReports.map((report) => {
            const pending = pendingMutation?.reportId === report.id;
            return (
              <article key={report.id} data-report-id={report.id}>
                <div className="report-detail-heading">
                  <div>
                    <b>{formatWrongParkingReason(report.reason_code)}</b>
                    <code>{report.id}</code>
                  </div>
                  <span className={`report-status status-${report.status.toLowerCase()}`}>
                    {formatWrongParkingReportStatus(report.status)}
                  </span>
                </div>
                <time dateTime={report.created_at}>{formatReportTime(report.created_at)}</time>
                {report.observed_plate_number && (
                  <p><strong>Biển số:</strong> {report.observed_plate_number}</p>
                )}
                {report.description && <p>{report.description}</p>}
                {evidenceUrls[report.id] ? (
                  <Image
                    className="report-evidence-image"
                    src={evidenceUrls[report.id]}
                    alt={`Ảnh hiện trường của report ${report.id}`}
                    width={720}
                    height={480}
                    unoptimized
                  />
                ) : report.evidence_storage_path ? (
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={loadingEvidenceId !== null}
                    onClick={() => void loadEvidence(report)}
                  >
                    {loadingEvidenceId === report.id ? "Đang tải ảnh…" : "Xem ảnh hiện trường"}
                  </button>
                ) : (
                  <p><strong>Ảnh hiện trường:</strong> Không có ảnh đính kèm</p>
                )}
                {report.resolution_note && (
                  <p className="resolution-note"><strong>Ghi chú xử lý:</strong> {report.resolution_note}</p>
                )}
                <p><strong>Kết quả xác minh:</strong> {formatVerificationOutcome(report.verification_outcome)}</p>
                <p><strong>Điểm:</strong> {report.reward_points} · {report.reward_status ?? "Không có reward"}</p>
                {report.duplicate_candidate_of_id && (
                  <p><strong>Report tương tự:</strong> <code>{report.duplicate_candidate_of_id}</code></p>
                )}

                {report.status === "OPEN" && (
                  <>
                    <label>
                      Kết quả xác minh (bắt buộc)
                      <select
                        value={resolutionOutcomes[report.id] ?? ""}
                        disabled={anyMutationPending}
                        onChange={(event) =>
                          setResolutionOutcomes((current) => ({
                            ...current,
                            [report.id]: event.target.value as Exclude<WrongParkingReportVerificationOutcome, "PENDING">,
                          }))
                        }
                      >
                        <option value="">Chọn kết quả</option>
                        <option value="CONFIRMED">Xác nhận hợp lệ</option>
                        <option value="REJECTED">Từ chối</option>
                        <option value="DUPLICATE">Trùng report</option>
                        <option value="UNVERIFIABLE">Không thể xác minh</option>
                      </select>
                    </label>
                    <label>
                      Ghi chú xử lý (không bắt buộc)
                      <textarea
                        value={resolutionNotes[report.id] ?? ""}
                        maxLength={500}
                        disabled={anyMutationPending}
                        onChange={(event) =>
                          setResolutionNotes((current) => ({
                            ...current,
                            [report.id]: event.target.value,
                          }))
                        }
                      />
                    </label>
                  </>
                )}

                <div className="report-detail-actions">
                  {report.status === "OPEN" ? (
                    <button
                      type="button"
                      className="primary-button"
                      disabled={anyMutationPending || !resolutionOutcomes[report.id]}
                      onClick={() =>
                        void onResolve(
                          report,
                          resolutionOutcomes[report.id] as Exclude<WrongParkingReportVerificationOutcome, "PENDING">,
                          resolutionNotes[report.id]?.trim() || null,
                        )
                      }
                    >
                      {pending && pendingMutation?.action === "resolve"
                        ? "Đang resolve…"
                        : "Resolve report"}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={anyMutationPending}
                      onClick={() => void onReopen(report)}
                    >
                      {pending && pendingMutation?.action === "reopen"
                        ? "Đang mở lại…"
                        : "Reopen report"}
                    </button>
                  )}
                  <button
                    type="button"
                    className="danger-button"
                    disabled={anyMutationPending}
                    onClick={() => setDeleteCandidate(report)}
                  >
                    {pending && pendingMutation?.action === "delete"
                      ? "Đang xóa…"
                      : "Xóa vĩnh viễn"}
                  </button>
                </div>
              </article>
            );
          })}
        </div>

        {deleteCandidate && (
          <div className="delete-confirm-backdrop">
            <section
              className="delete-confirm-dialog"
              role="alertdialog"
              aria-modal="true"
              aria-labelledby="delete-report-title"
              aria-describedby="delete-report-description"
            >
              <h3 id="delete-report-title">Xóa vĩnh viễn report?</h3>
              <p id="delete-report-description">
                Thao tác này xóa vĩnh viễn report khỏi database và không thể hoàn tác.
              </p>
              <dl>
                <div><dt>Report ID</dt><dd>{deleteCandidate.id}</dd></div>
                <div><dt>Ô đỗ</dt><dd>{formatParkingLocation(deleteCandidate.slot_id)}</dd></div>
              </dl>
              <div>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={anyMutationPending}
                  onClick={() => setDeleteCandidate(null)}
                >
                  Hủy
                </button>
                <button
                  type="button"
                  className="danger-button"
                  disabled={anyMutationPending}
                  onClick={() => void confirmDelete()}
                >
                  {pendingMutation?.action === "delete" ? "Đang xóa…" : "Xác nhận xóa vĩnh viễn"}
                </button>
              </div>
            </section>
          </div>
        )}
      </aside>
    </div>
  );
}
