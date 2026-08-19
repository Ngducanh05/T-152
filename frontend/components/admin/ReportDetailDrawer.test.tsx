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
    description: "Xe đỗ chéo vạch.",
    created_at: "2026-08-19T09:00:00Z",
    updated_at: "2026-08-19T09:00:00Z",
    resolved_at: null,
    resolved_by: null,
    resolution_note: null,
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
};

describe("ReportDetailDrawer", () => {
  it("shows actual slot status and reports newest first with friendly details", () => {
    const older = report("REPORT-OLD");
    const newer = report("REPORT-NEW", {
      reason_code: "BLOCKING_ACCESS",
      status: "RESOLVED",
      created_at: "2026-08-19T10:00:00Z",
      resolution_note: "Đã di chuyển xe.",
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
    expect(screen.getByText("Đã xử lý")).toBeVisible();
    expect(screen.getAllByText(/51A-123.45/)).toHaveLength(2);
  });

  it("requires explicit delete confirmation and cancel does not call delete", async () => {
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
    expect(dialog).toHaveTextContent("xóa vĩnh viễn report khỏi database");
    expect(dialog).toHaveTextContent("REPORT-DELETE");
    expect(dialog).toHaveTextContent("F1-D01");
    await user.click(within(dialog).getByRole("button", { name: "Hủy" }));
    expect(onDelete).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Xóa vĩnh viễn" }));
    await user.click(
      screen.getByRole("button", { name: "Xác nhận xóa vĩnh viễn" }),
    );
    expect(onDelete).toHaveBeenCalledOnce();
    expect(onDelete).toHaveBeenCalledWith(expect.objectContaining({ id: "REPORT-DELETE" }));
  });

  it("keeps reports visible on error and disables all mutations while one report is pending", () => {
    render(
      <ReportDetailDrawer
        slot={canonicalMap.slots.find((slot) => slot.id === "F1-D01")!}
        reports={[report("REPORT-1"), report("REPORT-2")]}
        loading={false}
        error="REPORT_VERSION_CONFLICT: hãy kiểm tra lại."
        pendingMutation={{ reportId: "REPORT-1", action: "resolve" }}
        {...defaultCallbacks}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("REPORT_VERSION_CONFLICT");
    expect(document.querySelectorAll(".report-detail-list article")).toHaveLength(2);
    for (const button of screen.getAllByRole("button", {
      name: /Resolve report|Đang resolve/,
    })) {
      expect(button).toBeDisabled();
    }
    for (const button of screen.getAllByRole("button", {
      name: "Xóa vĩnh viễn",
    })) {
      expect(button).toBeDisabled();
    }
  });

  it("keeps the report and confirmation open when hard delete fails", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn(async () => false);
    render(
      <ReportDetailDrawer
        slot={canonicalMap.slots.find((slot) => slot.id === "F1-D01")!}
        reports={[report("REPORT-FAILED-DELETE")]}
        loading={false}
        error="Không thể cập nhật report."
        pendingMutation={null}
        {...defaultCallbacks}
        onDelete={onDelete}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Xóa vĩnh viễn" }));
    await user.click(
      screen.getByRole("button", { name: "Xác nhận xóa vĩnh viễn" }),
    );

    expect(onDelete).toHaveBeenCalledOnce();
    expect(screen.getByRole("alertdialog", { name: "Xóa vĩnh viễn report?" })).toBeVisible();
    expect(document.querySelector('[data-report-id="REPORT-FAILED-DELETE"]')).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("Không thể cập nhật report");
  });
});
