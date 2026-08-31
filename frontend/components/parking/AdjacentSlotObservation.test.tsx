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

function observation(slotId: string): SlotObservation {
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
    evidence_storage_path: null,
    evidence_content_type: null,
    evidence_size_bytes: null,
    version: 0,
  };
}

function renderCard(onObserve = vi.fn(async (slotId: string) => observation(slotId))) {
  render(
    <AdjacentSlotObservation
      parkingSessionId="SESSION-001"
      parkedSlotId="F1-D03"
      slots={canonicalMap.slots}
      observedSlotIds={[]}
      pendingSlotId={null}
      onObserve={onObserve}
    />,
  );
  return onObserve;
}

async function openReview(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Giúp kiểm tra ngay" }));
  await user.click(screen.getByRole("button", { name: "Đã có xe" }));
}

describe("AdjacentSlotObservation", () => {
  it("moves from status question to review without immediately submitting", async () => {
    const user = userEvent.setup();
    const onObserve = renderCard();
    await openReview(user);
    expect(onObserve).not.toHaveBeenCalled();
    expect(screen.getByText("Đã có xe")).toBeVisible();
    expect(screen.getByRole("button", { name: "Gửi đóng góp" })).toBeVisible();
    expect(screen.queryByText(/\+10|10 điểm/)).not.toBeInTheDocument();
  });

  it("skips uncertain slots without a network mutation", async () => {
    const user = userEvent.setup();
    const onObserve = renderCard();
    await user.click(screen.getByRole("button", { name: "Giúp kiểm tra ngay" }));
    await user.click(screen.getByRole("button", { name: "Tôi không chắc" }));
    expect(onObserve).not.toHaveBeenCalled();
    expect(screen.getByText(/ô D04/)).toBeVisible();
  });

  it("provides separate camera/gallery inputs and forwards a selected image only after submit", async () => {
    const user = userEvent.setup();
    const objectUrl = vi.fn(() => "blob:adjacent-proof");
    vi.stubGlobal("URL", { ...URL, createObjectURL: objectUrl, revokeObjectURL: vi.fn() });
    const onObserve = renderCard();
    await openReview(user);
    const inputs = Array.from(document.querySelectorAll<HTMLInputElement>('input[type="file"]'));
    expect(inputs[0]).toHaveAttribute("accept", "image/*");
    expect(inputs[0]).toHaveAttribute("capture", "environment");
    expect(inputs[1]).toHaveAttribute("accept", "image/jpeg,image/png,image/webp,image/heic,image/heif");
    const evidence = new File(["jpeg"], "proof.jpg", { type: "image/jpeg" });
    await user.upload(inputs[1]!, evidence);
    expect(screen.getByText(/proof.jpg/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Gửi đóng góp" }));
    expect(onObserve).toHaveBeenCalledWith("F1-D02", "OCCUPIED", evidence);
    vi.unstubAllGlobals();
  });

  it("keeps selected status and image available after a failed submission", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:adjacent-proof", revokeObjectURL: vi.fn() });
    const onObserve = vi.fn().mockResolvedValueOnce(null).mockResolvedValueOnce(observation("F1-D02"));
    renderCard(onObserve);
    await openReview(user);
    const evidence = new File(["jpeg"], "retry.jpg", { type: "image/jpeg" });
    await user.upload(document.querySelectorAll<HTMLInputElement>('input[type="file"]')[1]!, evidence);
    await user.click(screen.getByRole("button", { name: "Gửi đóng góp" }));
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.getByText(/retry.jpg/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Gửi đóng góp" }));
    expect(onObserve).toHaveBeenCalledTimes(2);
    vi.unstubAllGlobals();
  });
});
