import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SlotObservation } from "@/lib/types";
import { canonicalMap } from "@/test/fixtures";

import { AdjacentSlotObservation } from "./AdjacentSlotObservation";

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
});

function pendingObservation(slotId: string): SlotObservation {
  return {
    id: `OBS-${slotId}`,
    observer_user_id: "USER-001",
    observer_session_id: "SESSION-001",
    slot_id: slotId,
    observed_status: "OCCUPIED",
    verification_status: "PENDING",
    reward_points: 10,
    reward_status: "PENDING",
    observed_slot_version: 0,
    created_at: "2026-08-23T10:00:00Z",
    expires_at: "2026-08-23T10:30:00Z",
    verified_at: null,
    verified_by: null,
    rejection_reason: null,
    version: 0,
  };
}

function renderCard(onObserve = vi.fn(async (slotId: string) => pendingObservation(slotId))) {
  render(
    <AdjacentSlotObservation
      parkingSessionId="SESSION-001"
      parkedSlotId="F1-D03"
      slots={canonicalMap.slots}
      observedSlotIds={[]}
      rewardPoints={10}
      pendingSlotId={null}
      onObserve={onObserve}
    />,
  );
  return onObserve;
}

describe("AdjacentSlotObservation", () => {
  it("starts collapsed with a friendly invitation and dismisses for this session", async () => {
    const user = userEvent.setup();
    renderCard();
    expect(screen.getByText("Cùng giúp bãi xe chính xác hơn nhé!")).toBeVisible();
    expect(screen.queryByText(/ô này đang trống hay đã có xe/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Để lúc khác" }));
    expect(screen.queryByText("Cùng giúp bãi xe chính xác hơn nhé!")).not.toBeInTheDocument();
  });

  it("asks one slot at a time without exposing its current status", async () => {
    const user = userEvent.setup();
    const onObserve = renderCard();
    await user.click(screen.getByRole("button", { name: "Giúp kiểm tra ngay" }));
    expect(screen.getByText(/Bạn nhìn giúp ô D02/)).toBeVisible();
    expect(screen.getByText("1/2")).toBeVisible();
    expect(screen.queryByText(/Hiện tại:/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tôi không chắc" }));
    expect(onObserve).not.toHaveBeenCalled();
    expect(screen.getByText(/Bạn nhìn giúp ô D04/)).toBeVisible();
  });

  it("does not ask again about a slot already observed in this parking session", async () => {
    const user = userEvent.setup();
    render(
      <AdjacentSlotObservation
        parkingSessionId="SESSION-001"
        parkedSlotId="F1-D03"
        slots={canonicalMap.slots}
        observedSlotIds={["F1-D02"]}
        rewardPoints={10}
        pendingSlotId={null}
        onObserve={vi.fn(async (slotId: string) => pendingObservation(slotId))}
      />,
    );

    expect(screen.getByText(/kiểm tra ô bên cạnh xe/)).toBeVisible();
    expect(screen.getByText("Tối đa +10 điểm chờ xác minh")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Giúp kiểm tra ngay" }));
    expect(screen.getByText(/Bạn nhìn giúp ô D04/)).toBeVisible();
    expect(screen.getByText("1/1")).toBeVisible();
    expect(screen.queryByText(/Bạn nhìn giúp ô D02/)).not.toBeInTheDocument();
  });

  it("hides the card when all adjacent slots were already observed", () => {
    const { container } = render(
      <AdjacentSlotObservation
        parkingSessionId="SESSION-001"
        parkedSlotId="F1-D03"
        slots={canonicalMap.slots}
        observedSlotIds={["F1-D02", "F1-D04"]}
        rewardPoints={10}
        pendingSlotId={null}
        onObserve={vi.fn(async (slotId: string) => pendingObservation(slotId))}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("submits once and describes the reward as pending", async () => {
    const user = userEvent.setup();
    const onObserve = renderCard();
    await user.click(screen.getByRole("button", { name: "Giúp kiểm tra ngay" }));
    await user.dblClick(screen.getByRole("button", { name: "Đã có xe" }));
    expect(onObserve).toHaveBeenCalledOnce();
    expect(onObserve).toHaveBeenCalledWith("F1-D02", "OCCUPIED");
    expect(await screen.findByText(/\+10 điểm sẽ được cộng nếu thông tin chính xác/)).toBeVisible();
    expect(screen.queryByText(/đã nhận điểm/i)).not.toBeInTheDocument();
  });
});
