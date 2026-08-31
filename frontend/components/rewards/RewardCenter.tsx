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
  const attempts = useRef<IdempotencyAttempt | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [confirmingItem, setConfirmingItem] = useState<RewardCatalogItem | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [redeemed, setRedeemed] = useState<RewardRedemptionResult | null>(null);
  const dialogCallbacks = useRef({ onClose, onRefresh, pendingId });

  useEffect(() => {
    dialogCallbacks.current = { onClose, onRefresh, pendingId };
  }, [onClose, onRefresh, pendingId]);

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
  const selectTab = (tab: Tab) => { setActiveTab(tab); setConfirmingItem(null); setMessage(null); };
  const moveTab = (direction: 1 | -1) => {
    const index = tabs.indexOf(activeTab);
    selectTab(tabs[(index + direction + tabs.length) % tabs.length]);
  };

  async function confirmRedeem() {
    if (!confirmingItem || pendingId) return;
    const key = getOrCreateIdempotencyKey(attempts, `${userId}:${confirmingItem.id}`);
    setPendingId(confirmingItem.id);
    setMessage(null);
    try {
      const result = await onRedeem(confirmingItem.id, key);
      clearIdempotencyKey(attempts);
      await onRefresh();
      setRedeemed(result);
      setConfirmingItem(null);
      setMessage("Đổi voucher thành công.");
    } catch (error) {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) clearIdempotencyKey(attempts);
      setMessage(formatApiErrorForOperator(error, "Không thể đổi điểm lúc này."));
    } finally { setPendingId(null); }
  }

  async function applyVoucher(voucher: ParkingVoucher) {
    if (pendingId) return;
    setPendingId(voucher.id);
    setMessage(null);
    try {
      await onApply(voucher.id);
      await onRefresh();
      setMessage("Voucher đã được áp dụng cho phiên đỗ xe hiện tại.");
    } catch (error) {
      setMessage(formatApiErrorForOperator(error, "Không thể áp dụng voucher."));
    } finally { setPendingId(null); }
  }

  const renderVoucherGroup = (title: string, values: ParkingVoucher[]) => values.length ? (
    <section className="reward-voucher-group"><h3>{title}</h3>{values.map((voucher) => (
      <article className="reward-voucher-card" key={voucher.id}>
        <div><b>{voucher.free_minutes_snapshot} phút miễn phí</b><span>{statusLabel(voucher.status)}</span></div>
        <small>Hết hạn: {formatDate(voucher.expires_at)}</small>
        {voucher.status === "ISSUED" && (activeSession ? <button type="button" disabled={pendingId !== null} onClick={() => void applyVoucher(voucher)}>{pendingId === voucher.id ? "Đang áp dụng…" : "Áp dụng voucher"}</button> : <p>Voucher này có thể dùng khi bạn có phiên đỗ xe đang hoạt động phù hợp.</p>)}
      </article>
    ))}</section>
  ) : null;

  return (
    <div className="reward-dialog-backdrop" onMouseDown={() => pendingId === null && onClose()}>
      <section ref={dialogRef} className="reward-dialog" role="dialog" aria-modal="true" aria-labelledby="parksmart-points-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="reward-dialog-header"><div><small>PARKSMART POINTS</small><h2 id="parksmart-points-title">Điểm ParkSmart</h2></div><button type="button" className="modal-close" onClick={onClose} disabled={pendingId !== null} aria-label="Đóng ParkSmart Points">×</button></header>
        <div className="reward-tabs" role="tablist" aria-label="ParkSmart Points">
          {tabs.map((tab) => <button key={tab} id={`points-tab-${tab}`} type="button" role="tab" aria-selected={activeTab === tab} aria-controls={`points-panel-${tab}`} tabIndex={activeTab === tab ? 0 : -1} onKeyDown={(event) => { if (event.key === "ArrowRight") moveTab(1); if (event.key === "ArrowLeft") moveTab(-1); }} onClick={() => selectTab(tab)}>{TAB_LABELS[tab]}</button>)}
        </div>
        <div id={`points-panel-${activeTab}`} role="tabpanel" aria-labelledby={`points-tab-${activeTab}`} className="reward-dialog-body">
          {activeTab === "overview" && <RewardSummaryCard summary={summary} />}
          {activeTab === "redeem" && redemptionEnabled && (redeemed ? <section className="reward-success" role="status"><h3>Đổi voucher thành công</h3><p>Voucher {redeemed.voucher.free_minutes_snapshot} phút đã được phát hành. Hạn dùng: {formatDate(redeemed.voucher.expires_at)}.</p><p>Số dư mới: {redeemed.available_points} điểm.</p><button type="button" onClick={() => { setRedeemed(null); selectTab("vouchers"); }}>Xem voucher của tôi</button></section> : confirmingItem ? <section className="reward-confirmation"><h3>Xác nhận đổi voucher</h3><p>Trừ {confirmingItem.points_cost} điểm để nhận {confirmingItem.free_minutes} phút đỗ xe miễn phí trong {confirmingItem.validity_days} ngày.</p><ul><li>Voucher chỉ dùng một lần, không có giá trị tiền mặt.</li><li>Phút chưa dùng hết sẽ không được chuyển sang lần sau.</li><li>Voucher hết hạn không tự động hoàn điểm.</li></ul><div><button type="button" onClick={() => setConfirmingItem(null)} disabled={pendingId !== null}>Quay lại</button><button type="button" className="primary-button" onClick={() => void confirmRedeem()} disabled={pendingId !== null}>{pendingId ? "Đang đổi…" : `Xác nhận đổi ${confirmingItem.points_cost} điểm`}</button></div></section> : <section className="reward-catalog">{catalog.length ? catalog.map((item) => { const missing = Math.max(0, item.points_cost - summary.available_points); return <article className="reward-catalog-item" key={item.id}><h3>{item.name}</h3><p>{item.points_cost} điểm · {item.free_minutes} phút miễn phí · hiệu lực {item.validity_days} ngày</p>{missing > 0 && <small>Còn thiếu {missing} điểm</small>}<button type="button" disabled={missing > 0 || pendingId !== null} onClick={() => setConfirmingItem(item)}>{missing > 0 ? "Chưa đủ điểm" : "Đổi voucher"}</button></article>; }) : <p>Hiện chưa có ưu đãi khả dụng.</p>}</section>)}
          {activeTab === "vouchers" && <section className="reward-vouchers">{renderVoucherGroup("Có thể dùng", vouchers.filter((value) => value.status === "ISSUED"))}{renderVoucherGroup("Đã sử dụng", vouchers.filter((value) => value.status === "APPLIED"))}{renderVoucherGroup("Đã hết hạn", vouchers.filter((value) => value.status === "EXPIRED"))}{renderVoucherGroup("Đã hủy", vouchers.filter((value) => value.status === "CANCELLED"))}{vouchers.length === 0 && <p>Chưa có voucher nào.</p>}</section>}
          {activeTab === "history" && <ul className="reward-ledger-list">{ledger.length ? ledger.map((entry) => <li key={entry.id}><div><b>{ledgerLabel(entry)}</b><small>{entry.status} · {formatDate(entry.created_at)}</small></div><strong className={entry.points_delta < 0 ? "negative" : "positive"}>{entry.points_delta > 0 ? "+" : ""}{entry.points_delta}</strong></li>) : <li>Chưa có lịch sử điểm.</li>}</ul>}
          {message && <p className="reward-dialog-message" role="status">{message}</p>}
        </div>
      </section>
    </div>
  );
}
