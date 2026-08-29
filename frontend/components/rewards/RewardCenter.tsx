"use client";

import { useRef, useState } from "react";
import { ApiError, formatApiErrorForOperator } from "@/lib/api";
import { clearIdempotencyKey, getOrCreateIdempotencyKey, type IdempotencyAttempt } from "@/lib/idempotency";
import type { ContributionRecord, ParkingVoucher, RewardCatalogItem, RewardRedemptionResult, RewardSummary } from "@/lib/types";
import { RewardSummaryCard } from "./RewardSummaryCard";

interface RewardCenterProps {
  userId: string;
  summary: RewardSummary;
  contributions: ContributionRecord[];
  catalog: RewardCatalogItem[];
  vouchers: ParkingVoucher[];
  onRedeem: (catalogItemId: string, idempotencyKey: string) => Promise<RewardRedemptionResult>;
  onRefresh: () => Promise<unknown>;
}

function voucherStatus(status: ParkingVoucher["status"]): string {
  return { ISSUED: "Sẵn sàng dùng cho ưu đãi đỗ xe sau này", APPLIED: "Đã sử dụng", EXPIRED: "Đã hết hạn (điểm không tự hoàn)", CANCELLED: "Đã hủy" }[status];
}

export function RewardCenter({ userId, summary, contributions, catalog, vouchers, onRedeem, onRefresh }: RewardCenterProps) {
  const attempts = useRef<IdempotencyAttempt | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function redeem(item: RewardCatalogItem) {
    const confirmation = `Đổi ${item.points_cost} điểm lấy ${item.free_minutes} phút đỗ xe miễn phí? Voucher dùng một lần, không có giá trị tiền mặt, có hiệu lực ${item.validity_days} ngày và hết hạn không tự hoàn điểm.`;
    if (!window.confirm(confirmation)) return;
    const key = getOrCreateIdempotencyKey(attempts, `${userId}:${item.id}`);
    setPendingId(item.id);
    setMessage(null);
    try {
      const result = await onRedeem(item.id, key);
      clearIdempotencyKey(attempts);
      await onRefresh();
      setMessage(`Đã phát hành voucher ${result.voucher.free_minutes_snapshot} phút. Hạn dùng: ${new Date(result.voucher.expires_at).toLocaleDateString("vi-VN")}.`);
    } catch (error) {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) clearIdempotencyKey(attempts);
      setMessage(formatApiErrorForOperator(error, "Không thể đổi điểm lúc này."));
    } finally {
      setPendingId(null);
    }
  }

  return <section className="reward-center" aria-label="ParkSmart Rewards">
    <RewardSummaryCard summary={summary} contributions={contributions} />
    <section className="reward-catalog"><h2>Đổi ưu đãi đỗ xe</h2>{catalog.map((item) => {
      const insufficient = summary.available_points < item.points_cost;
      return <article key={item.id} className="reward-catalog-item"><h3>{item.name}</h3><p>{item.points_cost} điểm · {item.free_minutes} phút miễn phí · hiệu lực {item.validity_days} ngày</p><button type="button" disabled={insufficient || pendingId !== null} onClick={() => void redeem(item)}>{pendingId === item.id ? "Đang đổi…" : insufficient ? "Chưa đủ điểm" : "Đổi điểm"}</button></article>;
    })}</section>
    <section className="voucher-wallet"><h2>Ví voucher</h2>{vouchers.length === 0 ? <p>Chưa có voucher nào.</p> : vouchers.map((voucher) => <article key={voucher.id}><b>{voucher.free_minutes_snapshot} phút miễn phí</b><p>{voucherStatus(voucher.status)}</p><small>Hết hạn: {new Date(voucher.expires_at).toLocaleString("vi-VN")}</small></article>)}</section>
    {message && <p role="status">{message}</p>}
  </section>;
}
