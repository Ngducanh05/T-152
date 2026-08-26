import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createClient: vi.fn(),
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: mocks.createClient,
}));

vi.mock("./config", () => ({
  getSupabasePublicConfig: () => ({
    url: "https://project.supabase.co",
    publishableKey: "public-test-key",
  }),
}));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  window.sessionStorage.clear();
  mocks.createClient.mockReturnValue({ auth: {} });
});

describe("createBrowserSupabaseClient", () => {
  it("stores the Supabase session in tab-scoped sessionStorage", async () => {
    const { createBrowserSupabaseClient } = await import("./client");

    createBrowserSupabaseClient();

    expect(mocks.createClient).toHaveBeenCalledOnce();
    const options = mocks.createClient.mock.calls[0]?.[2];
    expect(options.auth.storage).toBe(window.sessionStorage);
    expect(options.auth.persistSession).toBe(true);
    expect(options.auth.storageKey).toMatch(/^parksmart-auth:/);
  });

  it("reuses one client and one auth key inside the same tab", async () => {
    const { createBrowserSupabaseClient } = await import("./client");

    const first = createBrowserSupabaseClient();
    const second = createBrowserSupabaseClient();

    expect(second).toBe(first);
    expect(mocks.createClient).toHaveBeenCalledOnce();
    expect(window.sessionStorage.getItem("parksmart:supabase-auth-tab-id")).toBeTruthy();
  });
});
