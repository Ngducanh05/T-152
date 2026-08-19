import { describe, expect, it, vi } from "vitest";

import { ParkSmartApiClient } from "./api";

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("authenticated API client", () => {
  it("attaches the current bearer token to protected API requests", async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      jsonResponse({ success: true, data: [] }),
    );
    const api = new ParkSmartApiClient({
      baseUrl: "http://api.test/api/v1",
      fetcher,
    });
    api.setAuthProvider({
      getAccessToken: async () => "access-token-1",
      refreshAccessToken: async () => null,
    });

    await api.getSlots();

    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("Authorization")).toBe("Bearer access-token-1");
  });

  it("refreshes once after a 401 and retries with the new bearer token", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ error: "expired" }, 401))
      .mockResolvedValueOnce(
        jsonResponse({
          success: true,
          data: {
            id: "11111111-1111-4111-8111-111111111111",
            email: "user@example.com",
            full_name: "User",
            role: "user",
            parking_user_id: "USER-101",
            default_vehicle_id: "VEHICLE-101",
          },
        }),
      );
    const refreshAccessToken = vi.fn(async () => "access-token-2");
    const api = new ParkSmartApiClient({
      baseUrl: "http://api.test/api/v1",
      fetcher,
    });
    api.setAuthProvider({
      getAccessToken: async () => "access-token-1",
      refreshAccessToken,
    });

    const profile = await api.getCurrentUser();

    expect(profile.role).toBe("user");
    expect(refreshAccessToken).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledTimes(2);
    const retryHeaders = new Headers(fetcher.mock.calls[1]?.[1]?.headers);
    expect(retryHeaders.get("Authorization")).toBe("Bearer access-token-2");
  });

  it("invokes authentication failure when refresh cannot recover the session", async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      jsonResponse({ error: "expired" }, 401),
    );
    const onAuthenticationFailure = vi.fn(async () => undefined);
    const api = new ParkSmartApiClient({
      baseUrl: "http://api.test/api/v1",
      fetcher,
    });
    api.setAuthProvider({
      getAccessToken: async () => "expired-token",
      refreshAccessToken: async () => null,
      onAuthenticationFailure,
    });

    await expect(api.getSlots()).rejects.toMatchObject({ status: 401 });
    expect(fetcher).toHaveBeenCalledOnce();
    expect(onAuthenticationFailure).toHaveBeenCalledOnce();
  });
});
