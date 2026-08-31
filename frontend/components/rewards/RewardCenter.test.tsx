import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { RewardCenter } from "./RewardCenter";

afterEach(cleanup);

const summary = {
  available_points: 500,
  pending_points: 7,
  verified_contributions: 2,
  daily_pending_points: 7,
  daily_earned_points: 50,
  daily_limit_points: 100,
};
const catalog = [
  {
    id: "UNUSUAL",
    code: "ODD",
    name: "Ưu đãi từ catalog",
    points_cost: 123,
    free_minutes: 47,
    validity_days: 9,
    version: 0,
  },
];
const voucher = {
  id: "V-1",
  redemption_id: "R-1",
  catalog_code_snapshot: "ODD",
  points_cost_snapshot: 123,
  free_minutes_snapshot: 47,
  validity_days_snapshot: 9,
  status: "ISSUED" as const,
  issued_at: "2026-08-01T00:00:00Z",
  expires_at: "2026-08-10T00:00:00Z",
  applied_at: null,
  applied_session_id: null,
};

function renderCenter(overrides: Partial<ComponentProps<typeof RewardCenter>> = {}) {
  const onRedeem = vi.fn(async () => ({
    redemption: {
      id: "R-1",
      catalog_item_id: "UNUSUAL",
      points_cost_snapshot: 123,
      free_minutes_snapshot: 47,
      validity_days_snapshot: 9,
      status: "COMPLETED" as const,
      created_at: "2026-08-01T00:00:00Z",
    },
    voucher,
    available_points: 377,
  }));
  const onApply = vi.fn(async () => voucher);
  const onRefresh = vi.fn(async () => undefined);
  const onClose = vi.fn();
  render(
    <RewardCenter
      open
      userId="USER-001"
      summary={summary}
      ledger={[
        {
          id: "LEDGER-1",
          source_type: "VOUCHER_REDEMPTION",
          source_reference: "R-1",
          transaction_type: "VOUCHER_REDEMPTION",
          status: "POSTED",
          points_delta: -123,
          created_at: "2026-08-01T00:00:00Z",
          settled_at: "2026-08-01T00:00:00Z",
        },
      ]}
      catalog={catalog}
      vouchers={[voucher, { ...voucher, id: "V-2", status: "EXPIRED" }]}
      activeSession={null}
      redemptionEnabled
      onClose={onClose}
      onRedeem={onRedeem}
      onApply={onApply}
      onRefresh={onRefresh}
      {...overrides}
    />,
  );
  return { onApply, onClose, onRedeem, onRefresh };
}

describe("RewardCenter", () => {
  it("opens an accessible dialog with overview values and DB catalog values", async () => {
    const user = userEvent.setup();
    renderCenter();
    expect(screen.getByRole("dialog", { name: "Điểm ParkSmart" })).toBeVisible();
    expect(screen.getByText("500")).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Đổi điểm" }));
    expect(screen.getByText("Ưu đãi từ catalog")).toBeVisible();
    expect(screen.getByText(/123 điểm.*47 phút.*9 ngày/)).toBeVisible();
  });

  it("uses explicit confirmation before one idempotent redemption request", async () => {
    const user = userEvent.setup();
    const { onRedeem } = renderCenter();
    await user.click(screen.getByRole("tab", { name: "Đổi điểm" }));
    await user.click(screen.getByRole("button", { name: "Đổi voucher" }));
    expect(onRedeem).not.toHaveBeenCalled();
    const confirm = screen.getByRole("button", { name: "Xác nhận đổi 123 điểm" });
    await user.dblClick(confirm);
    expect(onRedeem).toHaveBeenCalledOnce();
    expect(onRedeem).toHaveBeenCalledWith("UNUSUAL", expect.any(String));
    expect(await screen.findByText("Đổi voucher thành công")).toBeVisible();
  });

  it("hides mutation UI while still exposing wallet and history when disabled", async () => {
    const user = userEvent.setup();
    renderCenter({ redemptionEnabled: false });
    expect(screen.queryByRole("tab", { name: "Đổi điểm" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Voucher của tôi" }));
    expect(screen.getAllByText("Có thể dùng").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("tab", { name: "Lịch sử" }));
    expect(screen.getByText("-123")).toBeVisible();
  });

  it("does not show a false success after a definitive redemption error", async () => {
    const user = userEvent.setup();
    const onRedeem = vi.fn(async () => {
      throw new ApiError({ code: "INSUFFICIENT_REWARD_POINTS", message: "Insufficient", status: 409 });
    });
    renderCenter({ onRedeem });
    await user.click(screen.getByRole("tab", { name: "Đổi điểm" }));
    await user.click(screen.getByRole("button", { name: "Đổi voucher" }));
    await user.click(screen.getByRole("button", { name: "Xác nhận đổi 123 điểm" }));
    expect(onRedeem).toHaveBeenCalledOnce();
    expect(screen.queryByText("Đổi voucher thành công")).not.toBeInTheDocument();
  });
});
