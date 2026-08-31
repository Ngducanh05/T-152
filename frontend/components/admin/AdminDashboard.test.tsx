import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SlotObservation, WrongParkingReport } from "@/lib/types";
import { canonicalMap, parkingStatus } from "@/test/fixtures";

import { AdminDashboard } from "./AdminDashboard";

const mocks = vi.hoisted(() => ({
  reports: [] as WrongParkingReport[],
  observations: [] as SlotObservation[],
  useParkSmartData: vi.fn(),
  getAdminEvents: vi.fn(async () => []),
  getAdminReports: vi.fn(),
  getAdminReport: vi.fn(),
  getAdminObservations: vi.fn(),
  verifyAdminObservation: vi.fn(),
  rejectAdminObservation: vi.fn(),
  resolveAdminReport: vi.fn(),
  reopenAdminReport: vi.fn(),
  deleteAdminReport: vi.fn(),
  resetDemo: vi.fn(),
  runFixedScenario: vi.fn(),
  parkSimulatedVehicle: vi.fn(),
  leaveSimulatedVehicle: vi.fn(),
  updateAdminSlotStatus: vi.fn(),
  getAdminReportEvidenceUrl: vi.fn(async () => ({ signed_url: "https://example.test/evidence.jpg" })),
}));

vi.mock("@/hooks/use-parksmart-data", () => ({
  useParkSmartData: mocks.useParkSmartData,
}));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    parkSmartApi: {
      getAdminEvents: mocks.getAdminEvents,
      getAdminReports: mocks.getAdminReports,
      getAdminReport: mocks.getAdminReport,
      getAdminObservations: mocks.getAdminObservations,
      verifyAdminObservation: mocks.verifyAdminObservation,
      rejectAdminObservation: mocks.rejectAdminObservation,
      resolveAdminReport: mocks.resolveAdminReport,
      reopenAdminReport: mocks.reopenAdminReport,
      deleteAdminReport: mocks.deleteAdminReport,
      resetDemo: mocks.resetDemo,
      runFixedScenario: mocks.runFixedScenario,
      parkSimulatedVehicle: mocks.parkSimulatedVehicle,
      leaveSimulatedVehicle: mocks.leaveSimulatedVehicle,
      updateAdminSlotStatus: mocks.updateAdminSlotStatus,
      getAdminReportEvidenceUrl: mocks.getAdminReportEvidenceUrl,
    },
  };
});
vi.mock("@/lib/report-updates", () => ({
  subscribeToWrongParkingReportUpdates: () => () => undefined,
}));

function report(id: string, createdAt: string): WrongParkingReport {
  return {
    id,
    reporter_user_id: "USER-001",
    slot_id: "F1-D01",
    reason_code: "CROSSED_LINE",
    status: "OPEN",
    observed_plate_number: null,
    description: null,
    evidence_storage_path: null,
    evidence_content_type: null,
    evidence_size_bytes: null,
    created_at: createdAt,
    updated_at: createdAt,
    resolved_at: null,
    resolved_by: null,
    resolution_note: null,
    verification_outcome: "PENDING",
    reward_points: 20,
    reward_status: "PENDING",
    duplicate_candidate_of_id: null,
    version: 0,
  };
}

beforeEach(() => {
  mocks.observations = [];
  mocks.reports = [
    report("REPORT-1", "2026-08-19T10:00:00Z"),
    report("REPORT-2", "2026-08-19T09:00:00Z"),
  ];
  mocks.getAdminReports.mockImplementation(async (filters: { status?: string; slotId?: string }) =>
    mocks.reports.filter((candidate) => {
      if (filters.status && candidate.status !== filters.status) return false;
      if (filters.slotId && candidate.slot_id !== filters.slotId) return false;
      return true;
    }),
  );
  mocks.getAdminReport.mockImplementation(async (reportId: string) =>
    mocks.reports.find((candidate) => candidate.id === reportId),
  );
  mocks.getAdminObservations.mockImplementation(async () => mocks.observations);
  mocks.updateAdminSlotStatus.mockImplementation(async (slotId: string, payload: { status: string }) => ({
    ...canonicalMap.slots.find((slot) => slot.id === slotId)!,
    status: payload.status,
    version: 2,
  }));
  mocks.resolveAdminReport.mockImplementation(async (reportId: string) => {
    const current = mocks.reports.find((candidate) => candidate.id === reportId)!;
    const resolved = {
      ...current,
      status: "RESOLVED" as const,
      version: current.version + 1,
      resolved_at: "2026-08-19T11:00:00Z",
      resolved_by: "DEMO-ADMIN",
    };
    mocks.reports = mocks.reports.map((candidate) =>
      candidate.id === reportId ? resolved : candidate,
    );
    return resolved;
  });
  mocks.useParkSmartData.mockReturnValue({
    map: canonicalMap,
    slots: canonicalMap.slots,
    status: parkingStatus,
    currentLocation: null,
    activeReservation: null,
    activeSession: null,
    lastUpdatedAt: "2026-08-19T10:00:00Z",
    loading: false,
    refreshing: false,
    error: null,
    refresh: vi.fn(async () => undefined),
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AdminDashboard report warnings", () => {
  it("does not render simulator controls", async () => {
    render(<AdminDashboard />);

    expect(await screen.findByTestId("parking-map")).toBeVisible();
    expect(screen.queryByText("MÔ PHỎNG BÃI XE")).not.toBeInTheDocument();
    expect(screen.queryByText("Điều khiển thủ công")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Chạy kịch bản cố định" })).not.toBeInTheDocument();
  });

  it("keeps the admin map and decrements warnings only after authoritative refetch", async () => {
    const user = userEvent.setup();
    render(<AdminDashboard />);

    expect(await screen.findByTestId("parking-map")).toBeVisible();
    const warnedSlot = await screen.findByRole("button", {
      name: /F1-D01.*2 báo cáo đang mở/,
    });
    await user.click(warnedSlot);
    const drawer = await screen.findByRole("dialog", { name: /Ô D01/ });
    expect(within(drawer).getAllByText(/Xe đỗ chéo vạch/)).toHaveLength(2);

    const firstReport = drawer.querySelector('[data-report-id="REPORT-1"]')!;
    await user.selectOptions(
      within(firstReport as HTMLElement).getByLabelText(/Kết quả xác minh/),
      "CONFIRMED",
    );
    await user.click(within(firstReport as HTMLElement).getByRole("button", { name: "Resolve report" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /F1-D01.*1 báo cáo đang mở/ })).toBeVisible(),
    );

    const secondReport = drawer.querySelector('[data-report-id="REPORT-2"]')!;
    await user.selectOptions(
      within(secondReport as HTMLElement).getByLabelText(/Kết quả xác minh/),
      "CONFIRMED",
    );
    await user.click(within(secondReport as HTMLElement).getByRole("button", { name: "Resolve report" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /F1-D01, Khu D/ })).not.toHaveClass(
        "has-open-reports",
      );
    });
    expect(mocks.resolveAdminReport).toHaveBeenCalledTimes(2);
  });

  it("opens a pending adjacent observation by clicking its yellow map slot", async () => {
    const user = userEvent.setup();
    mocks.observations = [{
      id: "OBS-1",
      observer_user_id: "USER-001",
      observer_session_id: "SESSION-001",
      slot_id: "F1-A02",
      observed_status: "OCCUPIED",
      verification_status: "PENDING",
      reward_points: 10,
      reward_status: "PENDING",
      observed_slot_version: 1,
      created_at: "2026-08-23T08:00:00Z",
      expires_at: "2026-08-23T08:30:00Z",
      verified_at: null,
      verified_by: null,
      rejection_reason: null,
      evidence_storage_path: null,
      evidence_content_type: null,
      evidence_size_bytes: null,
      version: 0,
    }];
    render(<AdminDashboard />);

    const warnedSlot = await screen.findByRole("button", {
      name: /F1-A02.*1 quan sát chờ xác minh/,
    });
    await user.click(warnedSlot);

    expect((await screen.findAllByRole("heading", { name: /Ô A02 — Tầng 1/ })).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /^Ô đỗ F1-A02/ })).toHaveClass("is-selected");
    expect(screen.getByText("Người gửi")).toBeVisible();
  });

  it("lets admin select a slot and save an authoritative status change", async () => {
    const user = userEvent.setup();
    render(<AdminDashboard />);

    await user.click(await screen.findByRole("button", { name: /F1-A02, Khu A/ }));
    const statusSelect = await screen.findByLabelText("Cập nhật trạng thái");
    await user.selectOptions(statusSelect, "OCCUPIED");
    await user.click(screen.getByRole("button", { name: "Lưu trạng thái" }));

    await waitFor(() => expect(mocks.updateAdminSlotStatus).toHaveBeenCalledWith(
      "F1-A02",
      { status: "OCCUPIED", expected_version: expect.any(Number) },
    ));
  });

  it("lets admin close the selected slot detail and clears the map highlight", async () => {
    const user = userEvent.setup();
    render(<AdminDashboard />);

    const slot = await screen.findByRole("button", { name: /F1-A02, Khu A/ });
    await user.click(slot);
    expect(await screen.findByRole("heading", { name: /Ô A02 — Tầng 1/ })).toBeVisible();
    expect(slot).toHaveClass("is-selected");

    await user.click(screen.getByRole("button", { name: "Đóng chi tiết ô đỗ" }));

    expect(screen.queryByText("CHI TIẾT Ô ĐỖ")).not.toBeInTheDocument();
    expect(slot).not.toHaveClass("is-selected");
  });
});
