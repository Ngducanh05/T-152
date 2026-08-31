import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";

import { ObservationEvidencePanel } from "./ObservationEvidencePanel";

const mocks = vi.hoisted(() => ({
  getAdminObservationEvidenceUrl: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    parkSmartApi: {
      getAdminObservationEvidenceUrl: mocks.getAdminObservationEvidenceUrl,
    },
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ObservationEvidencePanel", () => {
  it("requests a signed URL only after the admin clicks and displays the image", async () => {
    const user = userEvent.setup();
    mocks.getAdminObservationEvidenceUrl.mockResolvedValue({ signed_url: "https://example.test/evidence.jpg" });

    render(<ObservationEvidencePanel observationId="OBSERVATION-1" />);

    expect(mocks.getAdminObservationEvidenceUrl).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Xem ảnh minh chứng" }));

    await waitFor(() => expect(mocks.getAdminObservationEvidenceUrl).toHaveBeenCalledWith("OBSERVATION-1"));
    expect(await screen.findByRole("img", { name: "Ảnh minh chứng do người dùng gửi" })).toHaveAttribute(
      "src",
      "https://example.test/evidence.jpg",
    );
  });

  it("keeps the signed URL in component state and exposes a retry after an error", async () => {
    const user = userEvent.setup();
    mocks.getAdminObservationEvidenceUrl
      .mockRejectedValueOnce(new ApiError({
        code: "OBSERVATION_EVIDENCE_NOT_FOUND",
        message: "Missing evidence",
        status: 404,
      }))
      .mockResolvedValueOnce({ signed_url: "https://example.test/retry.jpg" });
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");

    render(<ObservationEvidencePanel observationId="OBSERVATION-2" />);
    await user.click(screen.getByRole("button", { name: "Xem ảnh minh chứng" }));

    expect(await screen.findByRole("alert")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByRole("img")).toHaveAttribute("src", "https://example.test/retry.jpg");
    expect(storageSpy).not.toHaveBeenCalled();
  });
});
