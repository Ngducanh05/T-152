import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RewardSummaryCard } from "./RewardSummaryCard";

afterEach(cleanup);

describe("RewardSummaryCard", () => {
  it("renders authoritative overview values without embedding a second history UI", () => {
    render(
      <RewardSummaryCard
        summary={{
          available_points: 20,
          pending_points: 10,
          verified_contributions: 1,
          daily_pending_points: 10,
          daily_earned_points: 20,
          daily_limit_points: 100,
        }}
      />,
    );

    expect(screen.getByText("20")).toBeVisible();
    expect(screen.getByText("Điểm đang chờ")).toBeVisible();
    expect(screen.getByText(/chưa thể dùng/i)).toBeVisible();
    expect(screen.queryByRole("button", { name: /lịch sử/i })).not.toBeInTheDocument();
  });
});
