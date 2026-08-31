"use client";

import type { RewardSummary } from "@/lib/types";

interface RewardSummaryCardProps {
  summary: RewardSummary;
}

export function RewardSummaryCard({ summary }: RewardSummaryCardProps) {
  return (
    <section className="reward-summary-card" aria-labelledby="reward-summary-title">
      <header>
        <span className="reward-summary-icon" aria-hidden="true">◆</span>
        <div>
          <small>PARKSMART POINTS</small>
          <h2 id="reward-summary-title">Điểm cộng đồng của bạn</h2>
        </div>
      </header>
      <div className="reward-summary-grid">
        <div><strong>{summary.available_points}</strong><span>Điểm khả dụng</span></div>
        <div><strong>{summary.pending_points}</strong><span>Điểm đang chờ</span></div>
        <div><strong>{summary.verified_contributions}</strong><span>Đóng góp đã xác minh</span></div>
      </div>
      <p className="reward-daily-progress">
        Hôm nay: {summary.daily_pending_points + summary.daily_earned_points}/{summary.daily_limit_points} điểm đã ghi nhận hoặc đang chờ
      </p>
      <p className="reward-summary-explainer">Điểm đang chờ chưa thể dùng. Chỉ điểm đã xác minh được cộng vào số dư khả dụng.</p>
    </section>
  );
}
