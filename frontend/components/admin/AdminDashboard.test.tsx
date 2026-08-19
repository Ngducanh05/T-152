import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WrongParkingReport } from "@/lib/types";
import { canonicalMap, parkingStatus } from "@/test/fixtures";

import { AdminDashboard } from "./AdminDashboard";

const mocks = vi.hoisted(() => ({
  reports: [] as WrongParkingReport[],
  useParkSmartData: vi.fn(),
  getAdminEvents: vi.fn(async () => []),
  getAdminReports: vi.fn(),
  getAdminReport: vi.fn(),
  resolveAdminReport: vi.fn(),
  reopenAdminReport: vi.fn(),
  deleteAdminReport: vi.fn(),
  resetDemo: vi.fn(),
  runFixedScenario: vi.fn(),
  parkSimulatedVehicle: vi.fn(),
  leaveSimulatedVehicle: vi.fn(),
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
      resolveAdminReport: mocks.resolveAdminReport,
      reopenAdminReport: mocks.reopenAdminReport,
      deleteAdminReport: mocks.deleteAdminReport,
      resetDemo: mocks.resetDemo,
      runFixedScenario: mocks.runFixedScenario,
      parkSimulatedVehicle: mocks.parkSimulatedVehicle,
      leaveSimulatedVehicle: mocks.leaveSimulatedVehicle,
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
    created_at: createdAt,
    updated_at: createdAt,
    resolved_at: null,
    resolved_by: null,
    resolution_note: null,
    version: 0,
  };
}

beforeEach(() => {
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
    await user.click(within(firstReport as HTMLElement).getByRole("button", { name: "Resolve report" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /F1-D01.*1 báo cáo đang mở/ })).toBeVisible(),
    );

    const secondReport = drawer.querySelector('[data-report-id="REPORT-2"]')!;
    await user.click(within(secondReport as HTMLElement).getByRole("button", { name: "Resolve report" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /F1-D01, Khu D/ })).not.toHaveClass(
        "has-open-reports",
      );
    });
    expect(mocks.resolveAdminReport).toHaveBeenCalledTimes(2);
  }, 10_000);
});
