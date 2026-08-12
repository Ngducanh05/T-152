import { describe, expect, it, vi } from "vitest";

import { errorEnvelope, jsonResponse, successEnvelope } from "@/test/fixtures";
import { ApiError, ParkSmartApiClient, parseApiResponse } from "./api";

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
