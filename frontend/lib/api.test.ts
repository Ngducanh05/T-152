import { describe, expect, it, vi } from "vitest";

import { ApiError, ParkSmartApiClient, parseApiResponse } from "./api";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("API envelope parsing", () => {
  it("returns data from a success envelope", async () => {
    const response = jsonResponse({
      success: true,
      data: { available: 12 },
      message: null,
    });

    await expect(parseApiResponse(response)).resolves.toEqual({ available: 12 });
  });

  it("throws typed ApiError for a failure envelope even when HTTP is ok", async () => {
    const response = jsonResponse({
      success: false,
      error: {
        code: "CURRENT_LOCATION_NOT_FOUND",
        message: "No confirmed location.",
        request_id: "request-123",
      },
    });

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
        {
          success: false,
          error: {
            code: "NOT_FOUND",
            message: "Optional resource does not exist.",
            request_id: "request-404",
          },
        },
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
