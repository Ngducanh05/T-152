"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError, formatApiErrorForOperator } from "@/lib/api";
import {
  clearIdempotencyKey,
  getOrCreateIdempotencyKey,
  type IdempotencyAttempt,
} from "@/lib/idempotency";
import type {
  ActiveParkingSession,
  ContributionRecord,
  ParkingVoucher,
  RewardCatalogItem,
  RewardRedemptionResult,
  RewardSummary,
  RewardTransaction,
} from "@/lib/types";

import { RewardSummaryCard } from "./RewardSummaryCard";

interface RewardCenterProps {
  userId: string;
  open: boolean;
  summary: RewardSummary;
  contributions: ContributionRecord[];
  catalog: RewardCatalogItem[];
  vouchers: ParkingVoucher[];
  rewardLedger: RewardTransaction[];
  rewardLedgerAvailable: boolean;
  activeSession: ActiveParkingSession | null;
  redemptionEnabled: boolean;
  onClose: () => void;
  onRedeem: (
    catalogItemId: string,
    idempotencyKey: string,
  ) => Promise<RewardRedemptionResult>;
  onApplyVoucher: (
    voucherId: string,
    sessionId: string,
    idempotencyKey: string,
  ) => Promise<ParkingVoucher>;
  onRefresh: () => Promise<unknown>;
}

type RewardTab = "overview" | "redeem" | "wallet" | "history";

const TABS: Array<{ id: RewardTab; label: string }> = [
  { id: "overview", label: "Tổng quan" },
  { id: "redeem", label: "Đổi điểm" },
  { id: "wallet", label: "Voucher của tôi" },
  { id: "history", label: "Lịch sử" },
];

function voucherStatus(status: ParkingVoucher["status"]): string {
  return {
    ISSUED: "Sẵn sàng sử dụng",
    APPLIED: "Đã áp dụng",
    EXPIRED: "Đã hết hạn (điểm không tự hoàn)",
    CANCELLED: "Đã hủy",
  }[status];
}

function isDefinitiveRejection(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.status >= 400 &&
    error.status < 500
  );
}

export function RewardCenter({
  userId,
  open,
  summary,
  contributions,
  catalog,
  vouchers,
  rewardLedger,
  rewardLedgerAvailable,
  activeSession,
  redemptionEnabled,
  onClose,
  onRedeem,
  onApplyVoucher,
  onRefresh,
}: RewardCenterProps) {
  const redemptionAttemptRef = useRef<IdempotencyAttempt | null>(null);
  const voucherApplyAttemptRef = useRef<IdempotencyAttempt | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);
  const initialFocusRef = useRef<HTMLButtonElement | null>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  const [tab, setTab] = useState<RewardTab>("overview");
  const [selectedItem, setSelectedItem] = useState<RewardCatalogItem | null>(null);
  const [redemptionPendingId, setRedemptionPendingId] = useState<string | null>(null);
  const [voucherApplyPendingId, setVoucherApplyPendingId] = useState<string | null>(null);
  const [redemptionResult, setRedemptionResult] =
    useState<RewardRedemptionResult | null>(null);
  const [appliedVoucher, setAppliedVoucher] = useState<ParkingVoucher | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [refreshWarning, setRefreshWarning] = useState<string | null>(null);
  const mutationPending =
    redemptionPendingId !== null || voucherApplyPendingId !== null;

  useEffect(() => {
    if (!open) return;

    previouslyFocusedRef.current = document.activeElement as HTMLElement | null;
    const focusTimer = window.setTimeout(() => initialFocusRef.current?.focus(), 0);

    return () => {
      window.clearTimeout(focusTimer);
      const previous = previouslyFocusedRef.current;
      if (previous?.isConnected) previous.focus();
    };
  }, [open]);

  useEffect(() => {
    if (open) return;
    const resetTimer = window.setTimeout(() => {
      setTab("overview");
      setSelectedItem(null);
      setRedemptionResult(null);
      setAppliedVoucher(null);
      setMessage(null);
      setRefreshWarning(null);
    }, 0);
    return () => window.clearTimeout(resetTimer);
  }, [open]);

  function requestClose() {
    if (!mutationPending) {
      setTab("overview");
      setSelectedItem(null);
      setRedemptionResult(null);
      setAppliedVoucher(null);
      setMessage(null);
      setRefreshWarning(null);
      onClose();
    }
  }

  function handleDialogKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      requestClose();
      return;
    }
    if (event.key !== "Tab") return;

    const focusable = Array.from(
      dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? [],
    ).filter((element) => !element.hasAttribute("hidden"));
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function refreshAfterMutation(warning: string) {
    try {
      await onRefresh();
    } catch {
      setRefreshWarning(warning);
    }
  }

  async function confirmRedemption() {
    const item = selectedItem;
    if (!item || redemptionPendingId !== null || !redemptionEnabled) return;

    const key = getOrCreateIdempotencyKey(
      redemptionAttemptRef,
      `${userId}:${item.id}`,
    );
    setRedemptionPendingId(item.id);
    setMessage(null);
    setRefreshWarning(null);

    let result: RewardRedemptionResult;
    try {
      result = await onRedeem(item.id, key);
    } catch (error) {
      if (isDefinitiveRejection(error)) {
        clearIdempotencyKey(redemptionAttemptRef);
      }
      setMessage(formatApiErrorForOperator(error, "Không thể đổi điểm lúc này."));
      setRedemptionPendingId(null);
      return;
    }

    clearIdempotencyKey(redemptionAttemptRef);
    setSelectedItem(null);
    setRedemptionResult(result);
    setRedemptionPendingId(null);
    setMessage(
      `Đã phát hành voucher ${result.voucher.free_minutes_snapshot} phút. Hạn dùng: ${new Date(
        result.voucher.expires_at,
      ).toLocaleDateString("vi-VN")}.`,
    );
    await refreshAfterMutation(
      "Voucher đã được phát hành nhưng dữ liệu mới nhất chưa tải lại được.",
    );
  }

  async function applyVoucher(voucher: ParkingVoucher) {
    if (!activeSession || voucherApplyPendingId !== null) return;

    const key = getOrCreateIdempotencyKey(
      voucherApplyAttemptRef,
      `${userId}:${voucher.id}:${activeSession.session_id}`,
    );
    setVoucherApplyPendingId(voucher.id);
    setMessage(null);
    setRefreshWarning(null);

    let result: ParkingVoucher;
    try {
      result = await onApplyVoucher(
        voucher.id,
        activeSession.session_id,
        key,
      );
    } catch (error) {
      if (isDefinitiveRejection(error)) {
        clearIdempotencyKey(voucherApplyAttemptRef);
      }
      setMessage(
        formatApiErrorForOperator(error, "Không thể áp dụng voucher lúc này."),
      );
      setVoucherApplyPendingId(null);
      return;
    }

    clearIdempotencyKey(voucherApplyAttemptRef);
    setAppliedVoucher(result);
    setVoucherApplyPendingId(null);
    setMessage(
      `Đã áp dụng voucher ${result.free_minutes_snapshot} phút cho phiên hiện tại.`,
    );
    await refreshAfterMutation(
      "Voucher đã được áp dụng nhưng dữ liệu mới nhất chưa tải lại được.",
    );
  }

  if (!open) return null;

  const currentSessionHasVoucher =
    vouchers.some(
      (voucher) =>
        voucher.status === "APPLIED" &&
        voucher.applied_session_id === activeSession?.session_id,
    ) || appliedVoucher?.applied_session_id === activeSession?.session_id;

  return (
    <div
      className="modal-backdrop points-modal-backdrop"
      onClick={requestClose}
      onKeyDown={handleDialogKeyDown}
    >
      <section
        ref={dialogRef}
        className="modal points-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="points-dialog-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          ref={initialFocusRef}
          type="button"
          className="modal-close"
          aria-label="Đóng ParkSmart Points"
          disabled={mutationPending}
          onClick={requestClose}
        >
          ×
        </button>
        <p className="eyebrow green">PARKSMART POINTS</p>
        <h1 id="points-dialog-title">Điểm và voucher của bạn</h1>

        <div className="points-tabs" role="tablist" aria-label="ParkSmart Points">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>

        {tab === "overview" && (
          <div role="tabpanel">
            <RewardSummaryCard summary={summary} contributions={contributions} />
            <p>
              ParkSmart Points ghi nhận các đóng góp đã được xác minh. Điểm đang
              chờ chưa nằm trong số dư khả dụng.
            </p>
          </div>
        )}

        {tab === "redeem" && (
          <section className="reward-catalog" role="tabpanel">
            <h2>Đổi ưu đãi đỗ xe</h2>
            {!redemptionEnabled && (
              <p role="status">Tính năng đổi điểm hiện tạm thời không khả dụng.</p>
            )}
            {catalog.map((item) => {
              const insufficient = summary.available_points < item.points_cost;
              return (
                <article key={item.id} className="reward-catalog-item">
                  <h3>{item.name}</h3>
                  <p>
                    {item.points_cost} điểm · {item.free_minutes} phút miễn phí ·
                    hiệu lực {item.validity_days} ngày
                  </p>
                  <button
                    type="button"
                    disabled={
                      insufficient || !redemptionEnabled || mutationPending
                    }
                    onClick={() => setSelectedItem(item)}
                  >
                    {insufficient ? "Chưa đủ điểm" : "Đổi điểm"}
                  </button>
                </article>
              );
            })}
            {selectedItem && (
              <section
                className="points-confirmation"
                aria-labelledby="redemption-confirmation-title"
              >
                <h3 id="redemption-confirmation-title">Xác nhận đổi điểm</h3>
                <p>
                  Đổi {selectedItem.points_cost} điểm lấy {selectedItem.free_minutes}
                  phút ưu đãi thời gian đỗ xe, hiệu lực {selectedItem.validity_days}
                  ngày.
                </p>
                <p>
                  Voucher chỉ dùng một lần, không có giá trị tiền mặt và khi hết
                  hạn sẽ không tự động hoàn điểm.
                </p>
                <div className="points-confirmation-actions">
                  <button
                    type="button"
                    disabled={mutationPending}
                    onClick={() => void confirmRedemption()}
                  >
                    {redemptionPendingId ? "Đang đổi…" : "Xác nhận"}
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={mutationPending}
                    onClick={() => setSelectedItem(null)}
                  >
                    Hủy
                  </button>
                </div>
              </section>
            )}
          </section>
        )}

        {tab === "wallet" && (
          <section className="voucher-wallet" role="tabpanel">
            <h2>Voucher của tôi</h2>
            {vouchers.length === 0 ? (
              <p>Chưa có voucher nào.</p>
            ) : (
              vouchers.map((voucher) => (
                <article key={voucher.id}>
                  <b>{voucher.free_minutes_snapshot} phút miễn phí</b>
                  <p>{voucherStatus(voucher.status)}</p>
                  <small>
                    Hết hạn: {new Date(voucher.expires_at).toLocaleString("vi-VN")}
                  </small>
                  {voucher.status === "APPLIED" && (
                    <p>Phiên đã áp dụng: {voucher.applied_session_id}</p>
                  )}
                  {voucher.status === "ISSUED" && !activeSession && (
                    <p>Cần có phiên đỗ xe đang hoạt động để áp dụng voucher.</p>
                  )}
                  {voucher.status === "ISSUED" &&
                    activeSession &&
                    !currentSessionHasVoucher && (
                      <button
                        type="button"
                        disabled={mutationPending}
                        onClick={() => void applyVoucher(voucher)}
                      >
                        {voucherApplyPendingId === voucher.id
                          ? "Đang áp dụng…"
                          : "Áp dụng cho phiên hiện tại"}
                      </button>
                    )}
                </article>
              ))
            )}
          </section>
        )}

        {tab === "history" && (
          <section className="points-history" role="tabpanel">
            <h2>Lịch sử Points</h2>
            {!rewardLedgerAvailable ? (
              <p>Lịch sử Points tạm thời không tải được.</p>
            ) : rewardLedger.length === 0 ? (
              <p>Chưa có giao dịch.</p>
            ) : (
              [...rewardLedger]
                .sort(
                  (left, right) =>
                    new Date(right.created_at).getTime() -
                    new Date(left.created_at).getTime(),
                )
                .map((transaction) => (
                  <article key={transaction.id}>
                    <div>
                      <b>{transaction.transaction_type}</b>
                      <time dateTime={transaction.created_at}>
                        {new Date(transaction.created_at).toLocaleString("vi-VN")}
                      </time>
                    </div>
                    <strong
                      className={
                        transaction.points_delta >= 0
                          ? "points-positive"
                          : "points-negative"
                      }
                    >
                      {transaction.points_delta > 0 ? "+" : ""}
                      {transaction.points_delta}
                    </strong>
                  </article>
                ))
            )}
          </section>
        )}

        {redemptionResult && (
          <p className="visually-hidden">
            Voucher {redemptionResult.voucher.id} đã được phát hành.
          </p>
        )}
        {message && <p role="status">{message}</p>}
        {refreshWarning && <p role="alert">{refreshWarning}</p>}
      </section>
    </div>
  );
}
