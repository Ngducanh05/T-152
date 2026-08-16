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
      observed_plate_number: "51A-123.45",
      description: "Xe đỗ chéo sang ô bên cạnh.",
    });
    await api.getAdminReports(10);

    expect(String(fetcher.mock.calls[0]?.[0])).toBe(
      "http://api.test/api/v1/reports/wrong-parking",
    );
    expect(fetcher.mock.calls[0]?.[1]?.body).toBe(
      JSON.stringify({
        user_id: "USER-001",
        slot_id: "F1-D01",
        observed_plate_number: "51A-123.45",
        description: "Xe đỗ chéo sang ô bên cạnh.",
      }),
    );
    expect(String(fetcher.mock.calls[1]?.[0])).toBe(
      "http://api.test/api/v1/admin/reports?limit=10",
    );
  });
});
