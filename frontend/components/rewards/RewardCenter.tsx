"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, formatApiErrorForOperator } from "@/lib/api";
import {
  clearIdempotencyKey,
  getOrCreateIdempotencyKey,
  type IdempotencyAttempt,
} from "@/lib/idempotency";
import type {
  ActiveParkingSession,
  ParkingVoucher,
  RewardCatalogItem,
  RewardLedgerEntry,
  RewardRedemptionResult,
  RewardSummary,
} from "@/lib/types";
import { RewardSummaryCard } from "./RewardSummaryCard";

type Tab = "overview" | "redeem" | "vouchers" | "history";

interface RewardCenterProps {
  open: boolean;
  userId: string;
  summary: RewardSummary;
  ledger: RewardLedgerEntry[];
  catalog: RewardCatalogItem[];
  vouchers: ParkingVoucher[];
  activeSession: ActiveParkingSession | null;
  redemptionEnabled: boolean;
  onClose: () => void;
  onRedeem: (catalogItemId: string, idempotencyKey: string) => Promise<RewardRedemptionResult>;
  onApply: (voucherId: string) => Promise<ParkingVoucher>;
  onRefresh: () => Promise<unknown>;
}

const TAB_LABELS: Record<Tab, string> = {
  overview: "Tổng quan",
  redeem: "Đổi điểm",
  vouchers: "Voucher của tôi",
  history: "Lịch sử",
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function statusLabel(status: ParkingVoucher["status"]) {
  return { ISSUED: "Có thể dùng", APPLIED: "Đã sử dụng", EXPIRED: "Đã hết hạn", CANCELLED: "Đã hủy" }[status];
}

function ledgerLabel(entry: RewardLedgerEntry) {
  if (entry.transaction_type === "VOUCHER_REDEMPTION") return "Đổi voucher";
  if (entry.transaction_type === "VOUCHER_REFUND") return "Hoàn điểm voucher";
  return entry.source_type === "ADJACENT_SLOT_OBSERVATION" ? "Quan sát ô bên cạnh" : "Đóng góp cộng đồng";
}

export function RewardCenter({
  open,
  userId,
  summary,
  ledger,
  catalog,
  vouchers,
  activeSession,
  redemptionEnabled,
  onClose,
  onRedeem,
  onApply,
  onRefresh,
}: RewardCenterProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({
    overview: null,
    redeem: null,
    vouchers: null,
    history: null,
  });
  const attempts = useRef<IdempotencyAttempt | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [confirmingItem, setConfirmingItem] = useState<RewardCatalogItem | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [redeemed, setRedeemed] = useState<RewardRedemptionResult | null>(null);
  const [appliedVoucher, setAppliedVoucher] = useState<ParkingVoucher | null>(null);
  const dialogCallbacks = useRef({ onClose, onRefresh, pendingId });

  const resetDialogState = useCallback(() => {
    setActiveTab("overview");
    setConfirmingItem(null);
    setRedeemed(null);
    setAppliedVoucher(null);
    setMessage(null);
  }, []);

  const closeDialog = useCallback(() => {
    resetDialogState();
    onClose();
  }, [onClose, resetDialogState]);

  useEffect(() => {
    dialogCallbacks.current = { onClose: closeDialog, onRefresh, pendingId };
  }, [closeDialog, onRefresh, pendingId]);

  useEffect(() => {
    if (!open) return;
    void dialogCallbacks.current.onRefresh().catch(() => undefined);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && dialogCallbacks.current.pendingId === null) {
        dialogCallbacks.current.onClose();
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>("button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex='-1'])"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", onKeyDown);
    window.setTimeout(() => dialogRef.current?.querySelector<HTMLElement>("button")?.focus(), 0);
    return () => { document.body.style.overflow = previousOverflow; window.removeEventListener("keydown", onKeyDown); };
  }, [open]);

  if (!open) return null;

  const tabs: Tab[] = redemptionEnabled ? ["overview", "redeem", "vouchers", "history"] : ["overview", "vouchers", "history"];
  const visibleActiveTab: Tab = !redemptionEnabled && activeTab === "redeem" ? "overview" : activeTab;
  const selectTab = (tab: Tab) => { setActiveTab(tab); setConfirmingItem(null); setMessage(null); };
  const moveTab = (tab: Tab, direction: 1 | -1) => {
    const index = tabs.indexOf(tab);
    const next = tabs[(index + direction + tabs.length) % tabs.length];
    selectTab(next);
    tabRefs.current[next]?.focus();
  };

  const displayedVouchers = appliedVoucher
    ? vouchers.map((voucher) => voucher.id === appliedVoucher.id ? appliedVoucher : voucher)
    : vouchers;
  const appliedToActiveSession = activeSession
    ? displayedVouchers.find((voucher) => voucher.status === "APPLIED" && voucher.applied_session_id === activeSession.session_id) ?? null
    : null;

  async function confirmRedeem() {
    if (!confirmingItem || pendingId) return;
    const key = getOrCreateIdempotencyKey(attempts, `${userId}:${confirmingItem.id}`);
    setPendingId(confirmingItem.id);
    setMessage(null);
    let result: RewardRedemptionResult;
    try {
      result = await onRedeem(confirmingItem.id, key);
    } catch (error) {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) clearIdempotencyKey(attempts);
      setMessage(formatApiErrorForOperator(error, "Không thể đổi điểm lúc này."));
      setPendingId(null);
      return;
    }

    // The server mutation has completed. Commit the local success state and
    // retire its logical idempotency attempt before any best-effort refresh.
    setRedeemed(result);
    clearIdempotencyKey(attempts);
    setConfirmingItem(null);
    setMessage("Đổi voucher thành công.");
    try {
      await onRefresh();
    } catch {
      setMessage("Đổi voucher thành công. Chưa thể tải lại dữ liệu mới nhất.");
    } finally {
      setPendingId(null);
    }
  }

  async function applyVoucher(voucher: ParkingVoucher) {
    if (pendingId) return;
    setPendingId(voucher.id);
    setMessage(null);
    let result: ParkingVoucher;
    try {
      result = await onApply(voucher.id);
    } catch (error) {
      setMessage(formatApiErrorForOperator(error, "Không thể áp dụng voucher."));
      setPendingId(null);
      return;
    }

    // Keep the returned applied voucher as local truth while the authoritative
    // refresh is unavailable, preventing a second apply attempt in the UI.
    setAppliedVoucher(result);
    setMessage("Voucher đã được áp dụng cho phiên đỗ xe hiện tại.");
    try {
      await onRefresh();
    } catch {
      setMessage("Voucher đã được áp dụng. Chưa thể tải lại dữ liệu mới nhất.");
    } finally {
      setPendingId(null);
    }
  }

  const renderVoucherGroup = (title: string, values: ParkingVoucher[]) => values.length ? (
    <section className="reward-voucher-group"><h3>{title}</h3>{values.map((voucher) => (
      <article className="reward-voucher-card" key={voucher.id}>
        <div><b>{voucher.free_minutes_snapshot} phút miễn phí</b><span>{statusLabel(voucher.status)}</span></div>
        <small>Hết hạn: {formatDate(voucher.expires_at)}</small>
        {voucher.status === "ISSUED" && (activeSession ? (
          appliedToActiveSession ? <p>Phiên đỗ xe này đã có voucher được áp dụng.</p> :
            <button type="button" disabled={pendingId !== null} onClick={() => void applyVoucher(voucher)}>{pendingId === voucher.id ? "Đang áp dụng…" : "Áp dụng voucher"}</button>
        ) : <p>Voucher này có thể dùng khi bạn có phiên đỗ xe đang hoạt động phù hợp.</p>)}
      </article>
    ))}</section>
  ) : null;

  return (
    <div className="reward-dialog-backdrop" onMouseDown={() => pendingId === null && closeDialog()}>
      <section ref={dialogRef} className="reward-dialog" role="dialog" aria-modal="true" aria-labelledby="parksmart-points-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="reward-dialog-header"><div><small>PARKSMART POINTS</small><h2 id="parksmart-points-title">Điểm ParkSmart</h2></div><button type="button" className="modal-close" onClick={closeDialog} disabled={pendingId !== null} aria-label="Đóng ParkSmart Points">×</button></header>
        <div className="reward-tabs" role="tablist" aria-label="ParkSmart Points">
          {tabs.map((tab) => <button key={tab} ref={(element) => { tabRefs.current[tab] = element; }} id={`points-tab-${tab}`} type="button" role="tab" aria-selected={visibleActiveTab === tab} aria-controls={`points-panel-${tab}`} tabIndex={visibleActiveTab === tab ? 0 : -1} onKeyDown={(event) => {
            if (event.key === "ArrowRight") { event.preventDefault(); moveTab(tab, 1); }
            else if (event.key === "ArrowLeft") { event.preventDefault(); moveTab(tab, -1); }
            else if (event.key === "Home") { event.preventDefault(); selectTab(tabs[0]); tabRefs.current[tabs[0]]?.focus(); }
            else if (event.key === "End") { event.preventDefault(); const last = tabs.at(-1)!; selectTab(last); tabRefs.current[last]?.focus(); }
          }} onClick={() => selectTab(tab)}>{TAB_LABELS[tab]}</button>)}
        </div>
        <div id={`points-panel-${visibleActiveTab}`} role="tabpanel" aria-labelledby={`points-tab-${visibleActiveTab}`} className="reward-dialog-body">
          {visibleActiveTab === "overview" && <RewardSummaryCard summary={summary} />}
          {visibleActiveTab === "redeem" && redemptionEnabled && (redeemed ? <section className="reward-success" role="status"><h3>Đổi voucher thành công</h3><p>Voucher {redeemed.voucher.free_minutes_snapshot} phút đã được phát hành. Hạn dùng: {formatDate(redeemed.voucher.expires_at)}.</p><p>Số dư mới: {redeemed.available_points} điểm.</p><button type="button" onClick={() => { setRedeemed(null); selectTab("vouchers"); }}>Xem voucher của tôi</button></section> : confirmingItem ? <section className="reward-confirmation"><h3>Xác nhận đổi voucher</h3><p>Trừ {confirmingItem.points_cost} điểm để nhận {confirmingItem.free_minutes} phút đỗ xe miễn phí trong {confirmingItem.validity_days} ngày.</p><ul><li>Voucher chỉ dùng một lần, không có giá trị tiền mặt.</li><li>Phút chưa dùng hết sẽ không được chuyển sang lần sau.</li><li>Voucher hết hạn không tự động hoàn điểm.</li></ul><div><button type="button" onClick={() => setConfirmingItem(null)} disabled={pendingId !== null}>Quay lại</button><button type="button" className="primary-button" onClick={() => void confirmRedeem()} disabled={pendingId !== null}>{pendingId ? "Đang đổi…" : `Xác nhận đổi ${confirmingItem.points_cost} điểm`}</button></div></section> : <section className="reward-catalog">{catalog.length ? catalog.map((item) => { const missing = Math.max(0, item.points_cost - summary.available_points); return <article className="reward-catalog-item" key={item.id}><h3>{item.name}</h3><p>{item.points_cost} điểm · {item.free_minutes} phút miễn phí · hiệu lực {item.validity_days} ngày</p>{missing > 0 && <small>Còn thiếu {missing} điểm</small>}<button type="button" disabled={missing > 0 || pendingId !== null} onClick={() => setConfirmingItem(item)}>{missing > 0 ? "Chưa đủ điểm" : "Đổi voucher"}</button></article>; }) : <p>Hiện chưa có ưu đãi khả dụng.</p>}</section>)}
          {visibleActiveTab === "vouchers" && <section className="reward-vouchers">{renderVoucherGroup("Có thể dùng", displayedVouchers.filter((value) => value.status === "ISSUED"))}{renderVoucherGroup("Đã sử dụng", displayedVouchers.filter((value) => value.status === "APPLIED"))}{renderVoucherGroup("Đã hết hạn", displayedVouchers.filter((value) => value.status === "EXPIRED"))}{renderVoucherGroup("Đã hủy", displayedVouchers.filter((value) => value.status === "CANCELLED"))}{displayedVouchers.length === 0 && <p>Chưa có voucher nào.</p>}</section>}
          {visibleActiveTab === "history" && <ul className="reward-ledger-list">{ledger.length ? ledger.map((entry) => <li key={entry.id}><div><b>{ledgerLabel(entry)}</b><small>{entry.status} · {formatDate(entry.created_at)}</small></div><strong className={entry.points_delta < 0 ? "negative" : "positive"}>{entry.points_delta > 0 ? "+" : ""}{entry.points_delta}</strong></li>) : <li>Chưa có lịch sử điểm.</li>}</ul>}
          {message && <p className="reward-dialog-message" role="status">{message}</p>}
        </div>
      </section>
    </div>
  );
}
