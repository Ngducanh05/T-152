import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  ParkingVoucher,
  RewardRedemptionResult,
  RewardTransaction,
} from "@/lib/types";

import { RewardCenter } from "./RewardCenter";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const summary = {
  available_points: 500,
  pending_points: 0,
  verified_contributions: 2,
  daily_pending_points: 0,
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
const voucher: ParkingVoucher = {
  id: "V-1",
  redemption_id: "R-1",
  catalog_code_snapshot: "ODD",
  points_cost_snapshot: 123,
  free_minutes_snapshot: 47,
  validity_days_snapshot: 9,
  status: "ISSUED",
  issued_at: "2026-08-01T00:00:00Z",
  expires_at: "2026-09-10T00:00:00Z",
  applied_at: null,
  applied_session_id: null,
};
const redemptionResult: RewardRedemptionResult = {
  redemption: {
    id: "R-1",
    catalog_item_id: "UNUSUAL",
    points_cost_snapshot: 123,
    free_minutes_snapshot: 47,
    validity_days_snapshot: 9,
    status: "COMPLETED",
    created_at: "2026-08-01T00:00:00Z",
  },
  voucher,
  available_points: 377,
};
const ledger: RewardTransaction[] = [
  {
    id: "TX-2",
    user_id: "USER-001",
    source_type: "VOUCHER_REDEMPTION",
    source_reference: "R-1",
    transaction_type: "VOUCHER_REDEMPTION",
    status: "POSTED",
    points_delta: -123,
    created_at: "2026-08-02T00:00:00Z",
    settled_at: "2026-08-02T00:00:00Z",
    metadata: {},
  },
  {
    id: "TX-1",
    user_id: "USER-001",
    source_type: "ADJACENT_SLOT_OBSERVATION",
    source_reference: "OBS-1",
    transaction_type: "CONTRIBUTION_REWARD",
    status: "EARNED",
    points_delta: 10,
    created_at: "2026-08-01T00:00:00Z",
    settled_at: "2026-08-01T00:00:00Z",
    metadata: {},
  },
];

function defaultProps(): ComponentProps<typeof RewardCenter> {
  return {
    userId: "USER-001",
    open: true,
    summary,
    contributions: [],
    catalog,
    vouchers: [voucher],
    rewardLedger: ledger,
    rewardLedgerAvailable: true,
    activeSession: {
      session_id: "SESSION-001",
      vehicle_id: "VEHICLE-001",
      slot_id: "F1-D03",
      destination_node_id: "F1-D03",
    },
    redemptionEnabled: true,
    onClose: vi.fn(),
    onRedeem: vi.fn(async () => redemptionResult),
    onApplyVoucher: vi.fn(async (_voucherId, sessionId) => ({
      ...voucher,
      status: "APPLIED" as const,
      applied_at: "2026-08-03T00:00:00Z",
      applied_session_id: sessionId,
    })),
    onRefresh: vi.fn(async () => undefined),
  };
}

function renderCenter(overrides: Partial<ComponentProps<typeof RewardCenter>> = {}) {
  const props = { ...defaultProps(), ...overrides };
  const view = render(<RewardCenter {...props} />);
  return { ...view, props };
}

async function openRedeemTab(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("tab", { name: "Đổi điểm" }));
}

describe("RewardCenter", () => {
  it("stays mounted while closed without rendering the dialog", () => {
    const { rerender, props } = renderCenter({ open: false });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    rerender(<RewardCenter {...props} open />);
    expect(screen.getByRole("dialog")).toBeVisible();
  });

  it("renders four tabs and authoritative unusual catalog values", async () => {
    const user = userEvent.setup();
    renderCenter();
    for (const label of ["Tổng quan", "Đổi điểm", "Voucher của tôi", "Lịch sử"]) {
      expect(screen.getByRole("tab", { name: label })).toBeVisible();
    }
    await openRedeemTab(user);
    expect(screen.getByText("Ưu đãi từ catalog")).toBeVisible();
    expect(screen.getByText(/123.*47.*9/)).toBeVisible();
  });

  it("uses an internal confirmation and cancel performs no mutation", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm");
    const { props } = renderCenter();
    await openRedeemTab(user);
    await user.click(screen.getByRole("button", { name: "Đổi điểm" }));
    expect(props.onRedeem).not.toHaveBeenCalled();
    expect(screen.getByText("Xác nhận đổi điểm")).toBeVisible();
    expect(screen.getAllByText(/123.*47.*9/)).toHaveLength(2);
    expect(screen.getByText(/một lần.*tiền mặt.*không.*hoàn điểm/i)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Hủy" }));
    expect(props.onRedeem).not.toHaveBeenCalled();
    expect(confirm).not.toHaveBeenCalled();
  });

  it("confirms once with a non-empty idempotency key", async () => {
    const user = userEvent.setup();
    const { props } = renderCenter();
    await openRedeemTab(user);
    await user.click(screen.getByRole("button", { name: "Đổi điểm" }));
    await user.click(screen.getByRole("button", { name: "Xác nhận" }));
    await waitFor(() => expect(props.onRedeem).toHaveBeenCalledOnce());
    expect(props.onRedeem).toHaveBeenCalledWith("UNUSUAL", expect.any(String));
    expect(vi.mocked(props.onRedeem).mock.calls[0][1]).not.toBe("");
  });

  it("disables mutation for insufficient balance or disabled redemption", async () => {
    const user = userEvent.setup();
    const { props, rerender } = renderCenter({
      summary: { ...summary, available_points: 122 },
    });
    await openRedeemTab(user);
    expect(screen.getByRole("button", { name: "Chưa đủ điểm" })).toBeDisabled();
    expect(props.onRedeem).not.toHaveBeenCalled();

    rerender(<RewardCenter {...props} summary={summary} redemptionEnabled={false} />);
    expect(screen.getByRole("button", { name: "Đổi điểm" })).toBeDisabled();
    expect(screen.getByText(/tạm thời không khả dụng/i)).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Voucher của tôi" }));
    expect(screen.getByText("47 phút miễn phí")).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Lịch sử" }));
    expect(screen.getByText("-123")).toBeVisible();
  });

  it("renders signed ledger values and distinguishes unavailable history", async () => {
    const user = userEvent.setup();
    const { rerender, props } = renderCenter();
    await user.click(screen.getByRole("tab", { name: "Lịch sử" }));
    expect(screen.getByText("+10")).toBeVisible();
    expect(screen.getByText("-123")).toBeVisible();

    rerender(
      <RewardCenter
        {...props}
        rewardLedger={[]}
        rewardLedgerAvailable={false}
      />,
    );
    expect(screen.getByText("Lịch sử Points tạm thời không tải được.")).toBeVisible();
    expect(screen.queryByText("Chưa có giao dịch.")).not.toBeInTheDocument();
  });

  it("offers voucher apply only for an eligible active session", async () => {
    const user = userEvent.setup();
    const { props, rerender } = renderCenter();
    await user.click(screen.getByRole("tab", { name: "Voucher của tôi" }));
    expect(screen.getByRole("button", { name: "Áp dụng cho phiên hiện tại" })).toBeVisible();

    rerender(<RewardCenter {...props} activeSession={null} />);
    expect(screen.queryByRole("button", { name: "Áp dụng cho phiên hiện tại" })).not.toBeInTheDocument();
    expect(screen.getByText(/Cần có phiên đỗ xe đang hoạt động/i)).toBeVisible();

    rerender(
      <RewardCenter
        {...props}
        vouchers={[
          voucher,
          {
            ...voucher,
            id: "V-APPLIED",
            status: "APPLIED",
            applied_at: "2026-08-03T00:00:00Z",
            applied_session_id: "SESSION-001",
          },
        ]}
      />,
    );
    expect(screen.queryByRole("button", { name: "Áp dụng cho phiên hiện tại" })).not.toBeInTheDocument();
    expect(screen.getByText(/Phiên đã áp dụng: SESSION-001/)).toBeVisible();
  });

  it("keeps an ambiguous redemption key through close and reopen", async () => {
    const user = userEvent.setup();
    const keys: string[] = [];
    const onRedeem = vi
      .fn<(catalogItemId: string, key: string) => Promise<RewardRedemptionResult>>()
      .mockImplementationOnce(async (_catalogItemId, key) => {
        keys.push(key);
        throw new TypeError("network lost");
      })
      .mockImplementationOnce(async (_catalogItemId, key) => {
        keys.push(key);
        return redemptionResult;
      });
    const { props, rerender } = renderCenter({ onRedeem });
    await openRedeemTab(user);
    await user.click(screen.getByRole("button", { name: "Đổi điểm" }));
    await user.click(screen.getByRole("button", { name: "Xác nhận" }));
    await waitFor(() => expect(onRedeem).toHaveBeenCalledTimes(1));

    rerender(<RewardCenter {...props} open={false} onRedeem={onRedeem} />);
    rerender(<RewardCenter {...props} open onRedeem={onRedeem} />);
    await openRedeemTab(user);
    await user.click(screen.getByRole("button", { name: "Đổi điểm" }));
    await user.click(screen.getByRole("button", { name: "Xác nhận" }));
    await waitFor(() => expect(onRedeem).toHaveBeenCalledTimes(2));
    expect(keys[0]).toBe(keys[1]);
  });

  it("keeps redemption success when refresh fails and does not retry", async () => {
    const user = userEvent.setup();
    const onRedeem = vi.fn(async () => redemptionResult);
    renderCenter({
      onRedeem,
      onRefresh: vi.fn(async () => {
        throw new Error("refresh failed");
      }),
    });
    await openRedeemTab(user);
    await user.click(screen.getByRole("button", { name: "Đổi điểm" }));
    await user.click(screen.getByRole("button", { name: "Xác nhận" }));
    expect(await screen.findByText(/Đã phát hành voucher 47 phút/i)).toBeVisible();
    expect(screen.getByText(/đã được phát hành nhưng dữ liệu mới nhất/i)).toBeVisible();
    expect(screen.queryByText(/Không thể đổi điểm/i)).not.toBeInTheDocument();
    expect(onRedeem).toHaveBeenCalledOnce();
  });

  it("keeps voucher-application success when refresh fails", async () => {
    const user = userEvent.setup();
    const onApplyVoucher = vi.fn(async (_voucherId, sessionId) => ({
      ...voucher,
      status: "APPLIED" as const,
      applied_at: "2026-08-03T00:00:00Z",
      applied_session_id: sessionId,
    }));
    renderCenter({
      onApplyVoucher,
      onRefresh: vi.fn(async () => {
        throw new Error("refresh failed");
      }),
    });
    await user.click(screen.getByRole("tab", { name: "Voucher của tôi" }));
    await user.click(screen.getByRole("button", { name: "Áp dụng cho phiên hiện tại" }));
    expect(await screen.findByText(/Đã áp dụng voucher 47 phút/i)).toBeVisible();
    expect(screen.getByText(/đã được áp dụng nhưng dữ liệu mới nhất/i)).toBeVisible();
    expect(screen.queryByText(/Không thể áp dụng voucher/i)).not.toBeInTheDocument();
    expect(onApplyVoucher).toHaveBeenCalledOnce();
  });
});
