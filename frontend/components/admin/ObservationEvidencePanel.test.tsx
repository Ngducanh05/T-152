import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
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

  it("resets evidence when switching to another observation", async () => {
    const user = userEvent.setup();
    const observationB = {
      ...observation,
      id: "OBSERVATION-002",
      evidence_storage_path: "slot-observations/OBSERVATION-002/image.jpg",
    };
    const request = vi
      .spyOn(parkSmartApi, "getAdminObservationEvidenceUrl")
      .mockImplementation(async (observationId) => ({
        signed_url: `https://signed.test/${observationId}.jpg`,
        expires_in: 300,
      }));
    const { rerender } = render(
      <ObservationEvidencePanel observation={observation} />,
    );

    await user.click(screen.getByRole("button", { name: "Xem ảnh" }));
    expect(await screen.findByAltText("Bằng chứng quan sát")).toHaveAttribute(
      "src",
      "https://signed.test/OBSERVATION-001.jpg",
    );

    rerender(<ObservationEvidencePanel observation={observationB} />);

    expect(screen.queryByAltText("Bằng chứng quan sát")).not.toBeInTheDocument();
    expect(request).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Xem ảnh" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Xem ảnh" }));
    expect(await screen.findByAltText("Bằng chứng quan sát")).toHaveAttribute(
      "src",
      "https://signed.test/OBSERVATION-002.jpg",
    );
    expect(screen.getByAltText("Bằng chứng quan sát")).not.toHaveAttribute(
      "src",
      "https://signed.test/OBSERVATION-001.jpg",
    );
  });

  it("ignores a late signed-url response from the previously selected observation", async () => {
    const user = userEvent.setup();
    const observationB = {
      ...observation,
      id: "OBSERVATION-002",
      evidence_storage_path: "slot-observations/OBSERVATION-002/image.jpg",
    };
    let resolveA!: (response: { signed_url: string; expires_in: number }) => void;
    let resolveB!: (response: { signed_url: string; expires_in: number }) => void;
    const promiseA = new Promise<{ signed_url: string; expires_in: number }>(
      (resolve) => {
        resolveA = resolve;
      },
    );
    const promiseB = new Promise<{ signed_url: string; expires_in: number }>(
      (resolve) => {
        resolveB = resolve;
      },
    );
    const request = vi
      .spyOn(parkSmartApi, "getAdminObservationEvidenceUrl")
      .mockImplementation((observationId) =>
        observationId === observation.id ? promiseA : promiseB,
      );
    const { rerender } = render(
      <ObservationEvidencePanel observation={observation} />,
    );

    await user.click(screen.getByRole("button", { name: "Xem ảnh" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith(observation.id));

    rerender(<ObservationEvidencePanel observation={observationB} />);
    await user.click(screen.getByRole("button", { name: "Xem ảnh" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith(observationB.id));

    await act(async () => {
      resolveB({
        signed_url: "https://signed.test/observation-b.jpg",
        expires_in: 300,
      });
      await promiseB;
    });
    expect(await screen.findByAltText("Bằng chứng quan sát")).toHaveAttribute(
      "src",
      "https://signed.test/observation-b.jpg",
    );

    await act(async () => {
      resolveA({
        signed_url: "https://signed.test/observation-a.jpg",
        expires_in: 300,
      });
      await promiseA;
    });
    expect(screen.getByAltText("Bằng chứng quan sát")).toHaveAttribute(
      "src",
      "https://signed.test/observation-b.jpg",
    );
    expect(screen.getByAltText("Bằng chứng quan sát")).not.toHaveAttribute(
      "src",
      "https://signed.test/observation-a.jpg",
    );
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
