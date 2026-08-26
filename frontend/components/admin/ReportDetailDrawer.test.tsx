import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WrongParkingReport } from "@/lib/types";
import { canonicalMap } from "@/test/fixtures";

import { ReportDetailDrawer } from "./ReportDetailDrawer";

afterEach(cleanup);

function report(
  id: string,
  overrides: Partial<WrongParkingReport> = {},
): WrongParkingReport {
  return {
    id,
    reporter_user_id: "USER-001",
    slot_id: "F1-D01",
    reason_code: "CROSSED_LINE",
    status: "OPEN",
    observed_plate_number: "51A-123.45",
    description: "Xe do cheo vach.",
    evidence_storage_path: null,
    evidence_content_type: null,
    evidence_size_bytes: null,
    created_at: "2026-08-19T09:00:00Z",
    updated_at: "2026-08-19T09:00:00Z",
    resolved_at: null,
    resolved_by: null,
    resolution_note: null,
    verification_outcome: "PENDING",
    reward_points: 20,
    reward_status: "PENDING",
    duplicate_candidate_of_id: null,
    version: 0,
    ...overrides,
  };
}

const defaultCallbacks = {
  onClose: vi.fn(),
  onRefresh: vi.fn(async () => undefined),
  onResolve: vi.fn(async () => true),
  onReopen: vi.fn(async () => true),
  onDelete: vi.fn(async () => true),
  onLoadEvidence: vi.fn(async () => null),
};

describe("ReportDetailDrawer", () => {
  it("shows reports newest first with verification and operational details", () => {
    const older = report("REPORT-OLD");
    const newer = report("REPORT-NEW", {
      reason_code: "BLOCKING_ACCESS",
      status: "RESOLVED",
      verification_outcome: "REJECTED",
      reward_status: "CANCELLED",
      created_at: "2026-08-19T10:00:00Z",
      resolution_note: "Rejected.",
      version: 1,
    });
    render(
      <ReportDetailDrawer
        slot={canonicalMap.slots.find((slot) => slot.id === "F1-D01")!}
        reports={[older, newer]}
        loading={false}
        error={null}
        pendingMutation={null}
        {...defaultCallbacks}
      />,
    );

    expect(screen.getByText(/Trạng thái ô thực tế/)).toHaveTextContent("Đang trống");
    const items = document.querySelectorAll(".report-detail-list article");
    expect(items[0]).toHaveAttribute("data-report-id", "REPORT-NEW");
    expect(items[1]).toHaveAttribute("data-report-id", "REPORT-OLD");
    expect(screen.getByText("Xe chắn lối đi")).toBeVisible();
    expect(screen.getByText("Bị từ chối")).toBeVisible();
    expect(screen.getAllByText(/51A-123.45/)).toHaveLength(2);
  });

  it("loads signed evidence URLs on demand", async () => {
    const user = userEvent.setup();
    const onLoadEvidence = vi.fn(async () => "https://signed.example/evidence.jpg");
    render(
      <ReportDetailDrawer
        slot={canonicalMap.slots.find((slot) => slot.id === "F1-D01")!}
        reports={[report("REPORT-EVIDENCE", { evidence_storage_path: "reports/x.jpg" })]}
        loading={false}
        error={null}
        pendingMutation={null}
        {...defaultCallbacks}
        onLoadEvidence={onLoadEvidence}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Xem ảnh hiện trường" }));
    expect(onLoadEvidence).toHaveBeenCalledOnce();
    expect(await screen.findByAltText("Ảnh hiện trường của report REPORT-EVIDENCE")).toBeVisible();
  });

  it("requires explicit delete confirmation", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn(async () => true);
    render(
      <ReportDetailDrawer
        slot={canonicalMap.slots.find((slot) => slot.id === "F1-D01")!}
        reports={[report("REPORT-DELETE")]}
        loading={false}
        error={null}
        pendingMutation={null}
        {...defaultCallbacks}
        onDelete={onDelete}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Xóa vĩnh viễn" }));
    const dialog = screen.getByRole("alertdialog", { name: "Xóa vĩnh viễn report?" });
    await user.click(within(dialog).getByRole("button", { name: "Hủy" }));
    expect(onDelete).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Xóa vĩnh viễn" }));
    await user.click(screen.getByRole("button", { name: "Xác nhận xóa vĩnh viễn" }));
    expect(onDelete).toHaveBeenCalledOnce();
  });

  it("disables mutations while one report is pending", () => {
    render(
      <ReportDetailDrawer
        slot={canonicalMap.slots.find((slot) => slot.id === "F1-D01")!}
        reports={[report("REPORT-1"), report("REPORT-2")]}
        loading={false}
        error="REPORT_VERSION_CONFLICT"
        pendingMutation={{ reportId: "REPORT-1", action: "resolve" }}
        {...defaultCallbacks}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("REPORT_VERSION_CONFLICT");
    for (const button of screen.getAllByRole("button", {
      name: /Resolve report|Xóa vĩnh viễn/,
    })) {
      expect(button).toBeDisabled();
    }
  });
});
