"use client";

import { useMemo, useState } from "react";

import {
  formatParkingLocation,
  formatSlotStatus,
  formatWrongParkingReason,
  formatWrongParkingReportStatus,
  formatWrongParkingReviewStatus,
} from "@/lib/parking-display";
import type { ParkingSlot, WrongParkingReport } from "@/lib/types";

export type ReportMutationAction = "resolve" | "reopen" | "delete" | "confirm" | "reject";
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
  onResolve: (report: WrongParkingReport, resolutionNote: string | null) => Promise<boolean>;
  onReopen: (report: WrongParkingReport) => Promise<boolean>;
  onDelete: (report: WrongParkingReport) => Promise<boolean>;
  onConfirm: (report: WrongParkingReport, reviewNote: string | null) => Promise<boolean>;
  onReject: (report: WrongParkingReport, reviewNote: string | null) => Promise<boolean>;
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
  onConfirm,
  onReject,
  onLoadEvidence,
}: ReportDetailDrawerProps) {
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [deleteCandidate, setDeleteCandidate] =
    useState<WrongParkingReport | null>(null);
  const [evidenceUrls, setEvidenceUrls] = useState<Record<string, string>>({});
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
    const url = await onLoadEvidence(report);
    if (url) {
      setEvidenceUrls((current) => ({ ...current, [report.id]: url }));
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
            <p className="eyebrow green">CHI TIET PHAN ANH</p>
            <h2 id="report-drawer-title">{formatParkingLocation(slot?.id)}</h2>
            <p>
              Trang thai o thuc te: <b>{slot ? formatSlotStatus(slot.status) : "Khong xac dinh"}</b>
            </p>
          </div>
          <button
            type="button"
            className="modal-close"
            aria-label="Dong chi tiet bao cao"
            onClick={onClose}
            disabled={anyMutationPending}
          >
            x
          </button>
        </header>

        <div className="drawer-refresh-row">
          <span>{orderedReports.length} bao cao tai o nay</span>
          <button type="button" onClick={() => void onRefresh()} disabled={loading || anyMutationPending}>
            {loading ? "Dang tai..." : "Tai lai"}
          </button>
        </div>

        {error && <div className="report-drawer-error" role="alert">{error}</div>}
        {loading && <p className="report-drawer-empty" role="status">Dang tai chi tiet bao cao...</p>}
        {!loading && orderedReports.length === 0 && (
          <p className="report-drawer-empty">Khong con bao cao tai o nay.</p>
        )}

        <div className="report-detail-list">
          {orderedReports.map((report) => {
            const pending = pendingMutation?.reportId === report.id;
            const note = notes[report.id]?.trim() || null;
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
                <p><strong>Reporter:</strong> {report.reporter_user_id}</p>
                <p><strong>Review:</strong> {formatWrongParkingReviewStatus(report.review_status)}</p>
                <p><strong>Operational:</strong> {formatWrongParkingReportStatus(report.status)}</p>
                {report.observed_plate_number && (
                  <p><strong>Bien so:</strong> {report.observed_plate_number}</p>
                )}
                {report.description && <p>{report.description}</p>}
                {report.review_note && (
                  <p className="resolution-note"><strong>Ghi chu review:</strong> {report.review_note}</p>
                )}
                {report.resolution_note && (
                  <p className="resolution-note"><strong>Ghi chu xu ly:</strong> {report.resolution_note}</p>
                )}

                {evidenceUrls[report.id] ? (
                  <img src={evidenceUrls[report.id]} alt={`Evidence for ${report.id}`} />
                ) : report.evidence_storage_path ? (
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={anyMutationPending}
                    onClick={() => void loadEvidence(report)}
                  >
                    Xem anh
                  </button>
                ) : (
                  <p>Report cu khong co anh.</p>
                )}

                {report.status === "OPEN" && (
                  <label>
                    Ghi chu (khong bat buoc)
                    <textarea
                      value={notes[report.id] ?? ""}
                      maxLength={500}
                      disabled={anyMutationPending}
                      onChange={(event) =>
                        setNotes((current) => ({
                          ...current,
                          [report.id]: event.target.value,
                        }))
                      }
                    />
                  </label>
                )}

                <div className="report-detail-actions">
                  {report.status === "OPEN" && report.review_status !== "CONFIRMED" && (
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={anyMutationPending}
                      onClick={() => void onConfirm(report, note)}
                    >
                      {pending && pendingMutation?.action === "confirm"
                        ? "Dang xac nhan..."
                        : "Confirm report"}
                    </button>
                  )}
                  {report.status === "OPEN" && (
                    <button
                      type="button"
                      className="danger-button"
                      disabled={anyMutationPending}
                      onClick={() => void onReject(report, note)}
                    >
                      {pending && pendingMutation?.action === "reject"
                        ? "Dang tu choi..."
                        : "Reject report"}
                    </button>
                  )}
                  {report.status === "OPEN" ? (
                    <button
                      type="button"
                      className="primary-button"
                      disabled={anyMutationPending}
                      onClick={() => void onResolve(report, note)}
                    >
                      {pending && pendingMutation?.action === "resolve"
                        ? "Dang resolve..."
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
                        ? "Dang mo lai..."
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
                      ? "Dang xoa..."
                      : "Xoa vinh vien"}
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
              <h3 id="delete-report-title">Xoa vinh vien report?</h3>
              <p id="delete-report-description">
                Thao tac nay xoa vinh vien report khoi database va co gang xoa anh bang chung.
              </p>
              <dl>
                <div><dt>Report ID</dt><dd>{deleteCandidate.id}</dd></div>
                <div><dt>O do</dt><dd>{formatParkingLocation(deleteCandidate.slot_id)}</dd></div>
              </dl>
              <div>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={anyMutationPending}
                  onClick={() => setDeleteCandidate(null)}
                >
                  Huy
                </button>
                <button
                  type="button"
                  className="danger-button"
                  disabled={anyMutationPending}
                  onClick={() => void confirmDelete()}
                >
                  {pendingMutation?.action === "delete" ? "Dang xoa..." : "Xac nhan xoa vinh vien"}
                </button>
              </div>
            </section>
          </div>
        )}
      </aside>
    </div>
  );
}
