import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RewardSummaryCard } from "./RewardSummaryCard";

afterEach(cleanup);

describe("RewardSummaryCard", () => {
  it("renders only the authoritative summary without a second history", () => {
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
    expect(screen.getByText("Đóng góp đã xác minh")).toBeVisible();
    expect(screen.getByText(/Hôm nay: 30\/100 điểm/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Xem lịch sử" })).not.toBeInTheDocument();
    expect(screen.queryByText("Quan sát ô bên cạnh")).not.toBeInTheDocument();
  });
});
