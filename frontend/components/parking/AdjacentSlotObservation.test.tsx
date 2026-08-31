import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SlotObservation } from "@/lib/types";
import { canonicalMap } from "@/test/fixtures";

import { AdjacentSlotObservation } from "./AdjacentSlotObservation";

let originalCreateObjectUrl: typeof URL.createObjectURL | undefined;
let originalRevokeObjectUrl: typeof URL.revokeObjectURL | undefined;
let createObjectUrl: ReturnType<typeof vi.fn>;
let revokeObjectUrl: ReturnType<typeof vi.fn>;

beforeEach(() => {
  originalCreateObjectUrl = URL.createObjectURL;
  originalRevokeObjectUrl = URL.revokeObjectURL;
  createObjectUrl = vi.fn((file: File) => `blob:${file.name}`);
  revokeObjectUrl = vi.fn();
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: createObjectUrl,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: revokeObjectUrl,
  });
});

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  if (originalCreateObjectUrl) {
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: originalCreateObjectUrl,
    });
  } else {
    Reflect.deleteProperty(URL, "createObjectURL");
  }
  if (originalRevokeObjectUrl) {
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: originalRevokeObjectUrl,
    });
  } else {
    Reflect.deleteProperty(URL, "revokeObjectURL");
  }
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
    evidence_storage_path: null,
    evidence_content_type: null,
    evidence_size_bytes: null,
    observed_slot_version: 0,
    created_at: "2026-08-23T10:00:00Z",
    expires_at: "2026-08-23T10:30:00Z",
    verified_at: null,
    verified_by: null,
    rejection_reason: null,
    version: 0,
  };
}

function defaultProps(): ComponentProps<typeof AdjacentSlotObservation> {
  return {
    parkingSessionId: "SESSION-001",
    parkedSlotId: "F1-D03",
    slots: canonicalMap.slots,
    observedSlotIds: [],
    pendingSlotId: null,
    onObserve: vi.fn(async (slotId: string) => pendingObservation(slotId)),
  };
}

function renderCard(
  overrides: Partial<ComponentProps<typeof AdjacentSlotObservation>> = {},
) {
  const props = { ...defaultProps(), ...overrides };
  const view = render(<AdjacentSlotObservation {...props} />);
  return { ...view, props };
}

async function openQuestion(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Giúp kiểm tra ngay" }));
}

async function chooseOccupied(user: ReturnType<typeof userEvent.setup>) {
  await openQuestion(user);
  await user.click(screen.getByRole("button", { name: "Đã có xe" }));
}

describe("AdjacentSlotObservation", () => {
  it("starts collapsed and dismisses only for the current session", async () => {
    const user = userEvent.setup();
    const { rerender, props } = renderCard();
    expect(screen.getByText("Cùng giúp bãi xe chính xác hơn nhé!")).toBeVisible();
    expect(screen.queryByText(/ô này đang trống hay đã có xe/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Để lúc khác" }));
    expect(screen.queryByText("Cùng giúp bãi xe chính xác hơn nhé!")).not.toBeInTheDocument();
    rerender(
      <AdjacentSlotObservation
        key="SESSION-002"
        {...props}
        parkingSessionId="SESSION-002"
      />,
    );
    expect(screen.getByText("Cùng giúp bãi xe chính xác hơn nhé!")).toBeVisible();
  });

  it("preserves slot filtering, progress, skip, and final state", async () => {
    const user = userEvent.setup();
    const { props } = renderCard();
    await openQuestion(user);
    expect(screen.getByText(/Bạn nhìn giúp ô D02/)).toBeVisible();
    expect(screen.getByText("1/2")).toBeVisible();
    expect(screen.queryByText(/Hiện tại:/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tôi không chắc" }));
    expect(props.onObserve).not.toHaveBeenCalled();
    expect(screen.getByText(/Bạn nhìn giúp ô D04/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Tôi không chắc" }));
    expect(screen.getByText("Cảm ơn bạn đã giúp ParkSmart!")).toBeVisible();

    cleanup();
    renderCard({ observedSlotIds: ["F1-D02"] });
    expect(screen.getByText(/kiểm tra ô bên cạnh xe/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Giúp kiểm tra ngay" }));
    expect(screen.getByText(/Bạn nhìn giúp ô D04/)).toBeVisible();
    expect(screen.getByText("1/1")).toBeVisible();
  });

  it("hides when all adjacent slots were already observed", () => {
    const { container } = renderCard({
      observedSlotIds: ["F1-D02", "F1-D04"],
    });
    expect(container).toBeEmptyDOMElement();
  });

  it("requires review and explicit submit with no evidence", async () => {
    const user = userEvent.setup();
    const { props } = renderCard();
    await openQuestion(user);
    await user.click(screen.getByRole("button", { name: "Ô đang trống" }));
    expect(props.onObserve).not.toHaveBeenCalled();
    expect(screen.getByText("Xem lại đóng góp")).toBeVisible();
    expect(screen.getByText(/Trạng thái đã chọn:/)).toHaveTextContent("Ô đang trống");
    await user.click(screen.getByRole("button", { name: "Gửi đóng góp" }));
    await waitFor(() => expect(props.onObserve).toHaveBeenCalledOnce());
    expect(props.onObserve).toHaveBeenCalledWith(
      "F1-D02",
      "AVAILABLE",
      undefined,
    );
    expect(screen.getByText(/theo dõi trong ParkSmart Points/i)).toBeVisible();
    expect(screen.queryByText(/\+10|Tối đa \+/)).not.toBeInTheDocument();
  });

  it("passes the selected evidence and guards double submit", async () => {
    const user = userEvent.setup();
    let resolveObservation!: (value: SlotObservation) => void;
    const onObserve = vi.fn(
      () => new Promise<SlotObservation>((resolve) => {
        resolveObservation = resolve;
      }),
    );
    renderCard({ onObserve });
    await chooseOccupied(user);
    const file = new File(["jpeg"], "space.jpg", { type: "image/jpeg" });
    await user.upload(
      screen.getByLabelText("Chọn ảnh quan sát từ thư viện"),
      file,
    );
    await user.dblClick(screen.getByRole("button", { name: "Gửi đóng góp" }));
    expect(onObserve).toHaveBeenCalledOnce();
    expect(onObserve).toHaveBeenCalledWith("F1-D02", "OCCUPIED", file);
    resolveObservation(pendingObservation("F1-D02"));
    expect(await screen.findByText(/theo dõi trong ParkSmart Points/i)).toBeVisible();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:space.jpg");
  });

  it("preserves selection, file, and preview after a failed submission", async () => {
    const user = userEvent.setup();
    const onObserve = vi.fn(async () => null);
    renderCard({ onObserve });
    await chooseOccupied(user);
    const file = new File(["jpeg"], "retry.jpg", { type: "image/jpeg" });
    await user.upload(screen.getByLabelText("Chọn ảnh quan sát từ thư viện"), file);
    await user.click(screen.getByRole("button", { name: "Gửi đóng góp" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Không thể gửi/);
    expect(screen.getByText("retry.jpg")).toBeVisible();
    expect(screen.getByAltText("Ảnh quan sát đã chọn")).toHaveAttribute(
      "src",
      "blob:retry.jpg",
    );
    expect(screen.getByText(/Đã có xe/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Gửi đóng góp" })).toBeEnabled();
    expect(revokeObjectUrl).not.toHaveBeenCalled();
  });

  it("revokes object URLs on replace, remove, next, dismiss, and unmount", async () => {
    const user = userEvent.setup();
    const first = new File(["a"], "first.jpg", { type: "image/jpeg" });
    const second = new File(["b"], "second.png", { type: "image/png" });
    const { unmount } = renderCard();
    await chooseOccupied(user);
    const input = screen.getByLabelText("Chọn ảnh quan sát từ thư viện");
    await user.upload(input, first);
    await user.upload(input, second);
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:first.jpg");
    await user.click(screen.getByRole("button", { name: "Xóa ảnh" }));
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:second.png");
    await user.upload(input, first);
    await user.click(screen.getByRole("button", { name: "Chọn lại" }));
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:first.jpg");

    await user.click(screen.getByRole("button", { name: "Tôi không chắc" }));
    await user.click(screen.getByRole("button", { name: "Đã có xe" }));
    const nextInput = screen.getByLabelText("Chọn ảnh quan sát từ thư viện");
    await user.upload(nextInput, second);
    unmount();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:second.png");
  });

  it("cleans a preview when dismissing after successful progression", async () => {
    const user = userEvent.setup();
    renderCard({ observedSlotIds: ["F1-D04"] });
    await chooseOccupied(user);
    const file = new File(["a"], "finish.webp", { type: "image/webp" });
    await user.upload(screen.getByLabelText("Chọn ảnh quan sát từ thư viện"), file);
    await user.click(screen.getByRole("button", { name: "Chọn lại" }));
    await user.click(screen.getByRole("button", { name: "Tôi không chắc" }));
    await user.click(screen.getByRole("button", { name: "Đóng" }));
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:finish.webp");
  });

  it.each([
    ["image/heic", "camera.heic"],
    ["image/heif", "camera.heif"],
  ])("accepts %s with metadata fallback", async (type, name) => {
    const user = userEvent.setup({ applyAccept: false });
    renderCard();
    await chooseOccupied(user);
    const file = new File(["heif-data"], name, { type });
    await user.upload(screen.getByLabelText("Chọn ảnh quan sát từ thư viện"), file);
    expect(screen.getByText(name)).toBeVisible();
    expect(screen.getByText(new RegExp(type))).toBeVisible();
    expect(screen.queryByAltText("Ảnh quan sát đã chọn")).not.toBeInTheDocument();
    expect(createObjectUrl).not.toHaveBeenCalled();
  });

  it("rejects invalid MIME and oversized files without destroying a valid photo", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderCard();
    await chooseOccupied(user);
    const input = screen.getByLabelText("Chọn ảnh quan sát từ thư viện");
    const valid = new File(["ok"], "valid.jpg", { type: "image/jpeg" });
    await user.upload(input, valid);
    await user.upload(input, new File(["bad"], "bad.gif", { type: "image/gif" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/JPEG.*5 MB/i);
    expect(screen.getByText("valid.jpg")).toBeVisible();
    expect(revokeObjectUrl).not.toHaveBeenCalled();

    const oversized = new File([new Uint8Array(5_000_001)], "huge.jpg", {
      type: "image/jpeg",
    });
    await user.upload(input, oversized);
    expect(screen.getByText("valid.jpg")).toBeVisible();
    expect(revokeObjectUrl).not.toHaveBeenCalled();
  });
});
