import { describe, expect, it, vi } from "vitest";

import { errorEnvelope, jsonResponse, successEnvelope } from "@/test/fixtures";
import {
  ApiError,
  ParkSmartApiClient,
  formatApiErrorForOperator,
  parseApiResponse,
} from "./api";

describe("API envelope parsing", () => {
  it("returns data from a success envelope", async () => {
    const response = jsonResponse(successEnvelope({ available: 12 }));

    await expect(parseApiResponse(response)).resolves.toEqual({ available: 12 });
  });

  it("throws typed ApiError for a failure envelope even when HTTP is ok", async () => {
    const response = jsonResponse(
      errorEnvelope(
        "CURRENT_LOCATION_NOT_FOUND",
        "No confirmed location.",
        "request-123",
      ),
    );

    const error = await parseApiResponse(response).catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      code: "CURRENT_LOCATION_NOT_FOUND",
      message: "No confirmed location.",
      requestId: "request-123",
      status: 200,
    });
  });
});

describe("database readiness", () => {
  it("checks the public database health URL with the supplied AbortSignal", async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      jsonResponse(successEnvelope({ database: "connected" })),
    );
    const authProvider = {
      getAccessToken: vi.fn(async () => "access-token"),
      refreshAccessToken: vi.fn(async () => "refreshed-token"),
    };
    const api = new ParkSmartApiClient({
      baseUrl: "http://api.test/api/v1/",
      fetcher,
      authProvider,
    });
    const controller = new AbortController();

    await expect(
      api.checkDatabaseHealth(controller.signal),
    ).resolves.toEqual({ database: "connected" });

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(String(fetcher.mock.calls[0]?.[0])).toBe(
      "http://api.test/api/v1/health/database",
    );
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
      signal: controller.signal,
    });
    expect(fetcher.mock.calls[0]?.[1]?.method).toBeUndefined();
    expect(fetcher.mock.calls[0]?.[1]?.body).toBeUndefined();
    expect(authProvider.getAccessToken).not.toHaveBeenCalled();
    expect(authProvider.refreshAccessToken).not.toHaveBeenCalled();
  });
});

describe("optional resources", () => {
  it("converts expected 404 responses to null", async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      jsonResponse(
        errorEnvelope(
          "NOT_FOUND",
          "Optional resource does not exist.",
          "request-404",
        ),
        404,
      ),
    );
    const api = new ParkSmartApiClient({
      baseUrl: "http://api.test/api/v1",
      fetcher,
    });

    await expect(api.getCurrentLocation("USER-001")).resolves.toBeNull();
    await expect(api.getActiveReservation("USER-001")).resolves.toBeNull();
    await expect(api.getActiveSession("USER-001")).resolves.toBeNull();
  });
});

describe("operator-safe errors", () => {
  it("shows the stable API code and request ID with understandable Vietnamese wording", () => {
    const error = new ApiError({
      code: "SLOT_NOT_AVAILABLE",
      message: "Slot version changed.",
      requestId: "request-conflict",
      status: 409,
    });

    expect(formatApiErrorForOperator(error)).toBe(
      "Không thể hoàn tất yêu cầu. Mã lỗi: SLOT_NOT_AVAILABLE. Mã yêu cầu: request-conflict.",
    );
  });

  it("does not invent request metadata for a network failure", () => {
    expect(formatApiErrorForOperator(new TypeError("fetch failed"))).toBe(
      "Không thể kết nối tới ParkSmart API. Vui lòng thử lại.",
    );
  });
});

describe("adjacent slot observations", () => {
  it("submits a typed status observation with optimistic version", async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      jsonResponse(successEnvelope({ id: "F1-D02", status: "OCCUPIED" })),
    );
    const api = new ParkSmartApiClient({
      baseUrl: "http://api.test/api/v1",
      fetcher,
    });

    await api.observeAdjacentSlot("F1-D02", {
      user_id: "USER-001",
      observed_status: "OCCUPIED",
      expected_slot_version: 7,
    });

    expect(String(fetcher.mock.calls[0]?.[0])).toBe(
      "http://api.test/api/v1/parking/slots/F1-D02/observation",
    );
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({
        user_id: "USER-001",
        observed_status: "OCCUPIED",
        expected_slot_version: 7,
      }),
    });
  });
});

describe("admin operations client", () => {
  it("uses typed simulator paths and payloads", async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      jsonResponse(successEnvelope([])),
    );
    const api = new ParkSmartApiClient({
      baseUrl: "http://api.test/api/v1",
      fetcher,
    });

    await api.parkSimulatedVehicle({
      slot_id: "F1-A01",
      vehicle_id: "SIM-CAR-01",
    });
    await api.leaveSimulatedVehicle({
      slot_id: "F1-A01",
      vehicle_id: "SIM-CAR-01",
    });
    await api.resetDemo();
    await api.runFixedScenario();

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "http://api.test/api/v1/simulator/park",
      "http://api.test/api/v1/simulator/leave",
      "http://api.test/api/v1/simulator/reset",
      "http://api.test/api/v1/simulator/run-scenario",
    ]);
    expect(fetcher.mock.calls[0]?.[1]?.body).toBe(
      JSON.stringify({ slot_id: "F1-A01", vehicle_id: "SIM-CAR-01" }),
    );
  });

  it("serializes admin event filters", async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      jsonResponse(successEnvelope([])),
    );
    const api = new ParkSmartApiClient({
      baseUrl: "http://api.test/api/v1",
      fetcher,
    });

    await api.getAdminEvents({
      limit: 10,
      zone_id: "D",
      event_type: "VEHICLE_PARKED",
      slot_id: "F1-D01",
    });

    expect(String(fetcher.mock.calls[0]?.[0])).toBe(
      "http://api.test/api/v1/admin/events?limit=10&zone_id=D&event_type=VEHICLE_PARKED&slot_id=F1-D01",
    );
  });

  it("updates a selected slot through the guarded admin status endpoint", async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      jsonResponse(successEnvelope({ id: "F2-D03", status: "OCCUPIED" })),
    );
    const api = new ParkSmartApiClient({
      baseUrl: "http://api.test/api/v1",
      fetcher,
    });

    await api.updateAdminSlotStatus("F2-D03", {
      status: "OCCUPIED",
      expected_version: 4,
    });

    expect(String(fetcher.mock.calls[0]?.[0])).toBe(
      "http://api.test/api/v1/admin/parking/slots/F2-D03/status",
    );
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
      method: "PATCH",
      body: JSON.stringify({ status: "OCCUPIED", expected_version: 4 }),
    });
  });

  it("submits and reads wrong-parking reports through typed endpoints", async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      jsonResponse(successEnvelope([])),
    );
    const api = new ParkSmartApiClient({
      baseUrl: "http://api.test/api/v1",
      fetcher,
    });

    await api.reportWrongParking({
      user_id: "USER-001",
      slot_id: "F1-D01",
      reason_code: "CROSSED_LINE",
      observed_plate_number: "51A-123.45",
      description: "Xe đỗ chéo sang ô bên cạnh.",
    });
    await api.getAdminReports({ status: "OPEN", slotId: "F1-D01", limit: 10 });
    await api.getAdminReport("REPORT-001");
    await api.resolveAdminReport("REPORT-001", {
      status: "RESOLVED",
      verification_outcome: "CONFIRMED",
      resolution_note: "Đã xử lý.",
      expected_version: 0,
    });
    await api.reopenAdminReport("REPORT-001", { expected_version: 1 });
    await api.deleteAdminReport("REPORT-001", { expected_version: 2 });

    expect(String(fetcher.mock.calls[0]?.[0])).toBe(
      "http://api.test/api/v1/reports/wrong-parking",
    );
    expect(fetcher.mock.calls[0]?.[1]?.body).toBe(
      JSON.stringify({
        user_id: "USER-001",
        slot_id: "F1-D01",
        reason_code: "CROSSED_LINE",
        observed_plate_number: "51A-123.45",
        description: "Xe đỗ chéo sang ô bên cạnh.",
      }),
    );
    expect(String(fetcher.mock.calls[1]?.[0])).toBe(
      "http://api.test/api/v1/admin/reports?status=OPEN&slot_id=F1-D01&limit=10",
    );
    expect(fetcher.mock.calls.slice(2).map(([input]) => String(input))).toEqual([
      "http://api.test/api/v1/admin/reports/REPORT-001",
      "http://api.test/api/v1/admin/reports/REPORT-001",
      "http://api.test/api/v1/admin/reports/REPORT-001/reopen",
      "http://api.test/api/v1/admin/reports/REPORT-001?expected_version=2",
    ]);
    expect(fetcher.mock.calls[2]?.[1]?.method).toBeUndefined();
    expect(fetcher.mock.calls[3]?.[1]?.method).toBe("PATCH");
    expect(fetcher.mock.calls[4]?.[1]?.method).toBe("POST");
    expect(fetcher.mock.calls[5]?.[1]?.method).toBe("DELETE");
  });

  it("uses multipart only when optional report evidence is selected", async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      jsonResponse(successEnvelope({ id: "REPORT-IMAGE" })),
    );
    const api = new ParkSmartApiClient({
      baseUrl: "http://api.test/api/v1",
      fetcher,
    });
    const evidence = new File(["image-bytes"], "scene.jpg", {
      type: "image/jpeg",
    });

    await api.reportWrongParking({
      user_id: "USER-001",
      slot_id: "F2-D03",
      reason_code: "BLOCKING_ACCESS",
      evidence,
    });

    const request = fetcher.mock.calls[0]?.[1];
    expect(request?.body).toBeInstanceOf(FormData);
    const body = request?.body as FormData;
    expect(body.get("user_id")).toBe("USER-001");
    expect(body.get("slot_id")).toBe("F2-D03");
    expect(body.get("reason_code")).toBe("BLOCKING_ACCESS");
    expect(body.get("evidence")).toBe(evidence);
    expect(new Headers(request?.headers).has("Content-Type")).toBe(false);
  });
});
