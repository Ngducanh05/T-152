import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { RewardCenter } from "./RewardCenter";

afterEach(cleanup);

const summary = { available_points: 500, pending_points: 0, verified_contributions: 2, daily_pending_points: 0, daily_earned_points: 50, daily_limit_points: 100 };
const catalog = [{ id: "UNUSUAL", code: "ODD", name: "Ưu đãi từ catalog", points_cost: 123, free_minutes: 47, validity_days: 9, version: 0 }];
const voucher = { id: "V-1", redemption_id: "R-1", catalog_code_snapshot: "ODD", points_cost_snapshot: 123, free_minutes_snapshot: 47, validity_days_snapshot: 9, status: "ISSUED" as const, issued_at: "2026-08-01T00:00:00Z", expires_at: "2026-08-10T00:00:00Z", applied_at: null, applied_session_id: null };

function renderCenter(overrides: Partial<ComponentProps<typeof RewardCenter>> = {}) {
  const onRedeem = vi.fn(async () => ({ redemption: { id: "R-1", catalog_item_id: "UNUSUAL", points_cost_snapshot: 123, free_minutes_snapshot: 47, validity_days_snapshot: 9, status: "COMPLETED" as const, created_at: "2026-08-01T00:00:00Z" }, voucher, available_points: 377 }));
  const onRefresh = vi.fn(async () => undefined);
  render(<RewardCenter userId="USER-001" summary={summary} contributions={[]} catalog={catalog} vouchers={[voucher, { ...voucher, id: "V-2", status: "EXPIRED" }]} onRedeem={onRedeem} onRefresh={onRefresh} {...overrides} />);
  return { onRedeem, onRefresh };
}

describe("RewardCenter", () => {
  it("renders supplied authoritative catalog values and an audit-visible voucher wallet", () => {
    renderCenter();
    expect(screen.getByText("Ưu đãi từ catalog")).toBeVisible();
    expect(screen.getByText(/123.*47.*9/)).toBeVisible();
    expect(screen.getByText(/Sẵn sàng dùng cho ưu đãi đỗ xe sau này/)).toBeVisible();
    expect(screen.getByText(/hết hạn.*không tự hoàn/i)).toBeVisible();
  });

  it("requires confirmation before redeeming, then refreshes authoritative state", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { onRedeem, onRefresh } = renderCenter();
    await user.click(screen.getByRole("button", { name: "Đổi điểm" }));
    const confirmation = confirm.mock.calls[0]?.[0] ?? "";
    expect(confirmation).toContain("123");
    expect(confirmation).toContain("47");
    expect(confirmation).toContain("9");
    expect(confirmation).toMatch(/một lần|single-use/i);
    expect(confirmation).toMatch(/tiền mặt|cash value/i);
    expect(confirmation).toMatch(/không tự hoàn|automatic refund/i);
    expect(onRedeem).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    await user.click(screen.getByRole("button", { name: "Đổi điểm" }));
    expect(onRedeem).toHaveBeenCalledWith("UNUSUAL", expect.any(String));
    expect(onRefresh).toHaveBeenCalledOnce();
    expect(await screen.findByRole("status")).toHaveTextContent(/phát hành voucher/i);
    confirm.mockRestore();
  });

  it("communicates known insufficient balance without attempting redemption", async () => {
    const user = userEvent.setup();
    const { onRedeem } = renderCenter({ summary: { ...summary, available_points: 122 } });
    expect(screen.getByRole("button", { name: "Chưa đủ điểm" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Chưa đủ điểm" }));
    expect(onRedeem).not.toHaveBeenCalled();
  });

  it("does not display success for a known business error", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onRedeem = vi.fn(async () => { throw new ApiError({ code: "INSUFFICIENT_REWARD_POINTS", message: "Insufficient", requestId: "r", status: 409 }); });
    renderCenter({ onRedeem });
    await user.click(screen.getByRole("button", { name: "Đổi điểm" }));
    expect(onRedeem).toHaveBeenCalledOnce();
    expect(screen.queryByText(/phát hành voucher/i)).not.toBeInTheDocument();
    vi.restoreAllMocks();
  });
});
