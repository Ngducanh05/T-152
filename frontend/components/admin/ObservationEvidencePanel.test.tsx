import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { parkSmartApi } from "@/lib/api";
import type { SlotObservation } from "@/lib/types";

import { ObservationEvidencePanel } from "./ObservationEvidencePanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const observation: SlotObservation = {
  id: "OBSERVATION-001",
  observer_user_id: "USER-001",
  observer_session_id: "SESSION-001",
  slot_id: "F1-D02",
  observed_status: "OCCUPIED",
  verification_status: "PENDING",
  reward_points: 10,
  reward_status: "PENDING",
  evidence_storage_path: "slot-observations/OBSERVATION-001/image.jpg",
  evidence_content_type: "image/jpeg",
  evidence_size_bytes: 100,
  observed_slot_version: 1,
  created_at: "2026-08-23T10:00:00Z",
  expires_at: "2026-08-23T10:30:00Z",
  verified_at: null,
  verified_by: null,
  rejection_reason: null,
  version: 0,
};

describe("ObservationEvidencePanel", () => {
  it("loads and displays a signed URL only after the operator clicks", async () => {
    const user = userEvent.setup();
    const request = vi
      .spyOn(parkSmartApi, "getAdminObservationEvidenceUrl")
      .mockResolvedValue({
        signed_url: "https://signed.test/observation.jpg",
        expires_in: 300,
      });
    render(<ObservationEvidencePanel observation={observation} />);

    expect(request).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Xem ảnh" }));
    expect(request).toHaveBeenCalledOnce();
    expect(await screen.findByAltText("Bằng chứng quan sát")).toHaveAttribute(
      "src",
      "https://signed.test/observation.jpg",
    );
  });

  it("keeps signing failures local", async () => {
    const user = userEvent.setup();
    vi.spyOn(parkSmartApi, "getAdminObservationEvidenceUrl").mockRejectedValue(
      new Error("signing unavailable"),
    );
    render(<ObservationEvidencePanel observation={observation} />);

    await user.click(screen.getByRole("button", { name: "Xem ảnh" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Không thể tải ảnh bằng chứng.",
    );
    expect(screen.getByRole("button", { name: "Xem ảnh" })).toBeEnabled();
  });

  it("renders nothing when the observation has no evidence", () => {
    const { container } = render(
      <ObservationEvidencePanel
        observation={{
          ...observation,
          evidence_storage_path: null,
          evidence_content_type: null,
          evidence_size_bytes: null,
        }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
