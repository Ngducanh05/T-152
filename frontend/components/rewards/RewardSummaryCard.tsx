"use client";

import { useState } from "react";

import { formatParkingLocation } from "@/lib/parking-display";
import type { ContributionRecord, RewardSummary } from "@/lib/types";

interface RewardSummaryCardProps {
  summary: RewardSummary;
  contributions: ContributionRecord[];
}

function contributionLabel(contribution: ContributionRecord) {
  return contribution.source_type === "ADJACENT_SLOT_OBSERVATION"
    ? "Quan sát ô bên cạnh"
    : "Report xe đỗ sai";
}

function statusLabel(status: ContributionRecord["status"]) {
  if (status === "EARNED") return "Đã xác minh";
  if (status === "CANCELLED") return "Không được xác nhận";
  if (status === "PENDING") return "Chờ xác minh";
  return "Không có điểm thưởng";
}

export function RewardSummaryCard({
  summary,
  contributions,
}: RewardSummaryCardProps) {
  const [showHistory, setShowHistory] = useState(false);

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
      <button
        type="button"
        className="reward-history-toggle"
        aria-expanded={showHistory}
        onClick={() => setShowHistory((current) => !current)}
      >
        {showHistory ? "Ẩn lịch sử" : "Xem lịch sử"}
      </button>
      {showHistory && (
        <ul className="reward-history" aria-label="Lịch sử đóng góp">
          {contributions.length === 0 ? (
            <li>Chưa có đóng góp nào.</li>
          ) : (
            contributions.map((contribution) => (
              <li key={`${contribution.source_type}:${contribution.source_reference}`}>
                <div>
                  <b>{contributionLabel(contribution)}</b>
                  <span>{formatParkingLocation(contribution.slot_id)}</span>
                  <time dateTime={contribution.created_at}>
                    {new Intl.DateTimeFormat("vi-VN", {
                      dateStyle: "short",
                      timeStyle: "short",
                    }).format(new Date(contribution.created_at))}
                  </time>
                </div>
                <div>
                  <strong>{contribution.points > 0 ? `+${contribution.points}` : "0"}</strong>
                  <span>{statusLabel(contribution.status)}</span>
                </div>
              </li>
            ))
          )}
        </ul>
      )}
    </section>
  );
}
