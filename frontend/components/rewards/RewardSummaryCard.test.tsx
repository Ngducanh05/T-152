import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { RewardSummaryCard } from "./RewardSummaryCard";

afterEach(cleanup);

describe("RewardSummaryCard", () => {
  it("renders authoritative summary and friendly contribution history", async () => {
    const user = userEvent.setup();
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
        contributions={[
          {
            id: "REWARD-001",
            source_type: "ADJACENT_SLOT_OBSERVATION",
            source_reference: "OBSERVATION-001",
            observer_session_id: "SESSION-001",
            floor_id: "F2",
            slot_id: "F2-D02",
            points: 10,
            status: "PENDING",
            created_at: "2026-08-23T10:00:00Z",
            settled_at: null,
          },
        ]}
      />,
    );

    expect(screen.getByText("20")).toBeVisible();
    expect(screen.getByText("Điểm đang chờ")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Xem lịch sử" }));
    expect(screen.getByText("Quan sát ô bên cạnh")).toBeVisible();
    expect(screen.getByText(/F2-D02/)).toBeVisible();
    expect(screen.getByText("Chờ xác minh")).toBeVisible();
    expect(screen.queryByText(/tiền|phút đỗ/i)).not.toBeInTheDocument();
  });
});
