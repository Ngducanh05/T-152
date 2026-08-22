import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useEffect } from "react";

import type { AuthenticatedProfile } from "@/lib/auth";
import { AuthProvider, useAuth } from "./AuthProvider";

const mocks = vi.hoisted(() => ({
  createBrowserSupabaseClient: vi.fn(),
  setAuthProvider: vi.fn(),
  getCurrentUser: vi.fn(),
  onboardCurrentUser: vi.fn(),
  addVehicle: vi.fn(),
}));

vi.mock("@/lib/supabase/client", () => ({
  createBrowserSupabaseClient: mocks.createBrowserSupabaseClient,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    parkSmartApi: {
      setAuthProvider: mocks.setAuthProvider,
      getCurrentUser: mocks.getCurrentUser,
      onboardCurrentUser: mocks.onboardCurrentUser,
      addVehicle: mocks.addVehicle,
    },
  };
});

const profile: AuthenticatedProfile = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "user@example.com",
  full_name: "User",
  role: "user",
  parking_user_id: "USER-NEW",
  default_vehicle_id: null,
};

function createSupabaseMock(
  signUpResult: {
    data: {
      user: { id: string } | null;
      session: { access_token: string } | null;
    };
    error: null;
  },
) {
  const auth: SupabaseAuthMock = {
    getSession: vi.fn(async () => ({ data: { session: null }, error: null })),
    refreshSession: vi.fn(async () => ({ data: { session: null }, error: null })),
    onAuthStateChange: vi.fn(() => ({
      data: {
        subscription: {
          unsubscribe: vi.fn(),
        },
      },
    })),
    signInWithPassword: vi.fn(),
    signOut: vi.fn(async () => ({ error: null })),
    signUp: vi.fn(async () => signUpResult),
  };

  return { auth };
}

type SupabaseAuthMock = {
  getSession: ReturnType<typeof vi.fn>;
  refreshSession: ReturnType<typeof vi.fn>;
  onAuthStateChange: ReturnType<typeof vi.fn>;
  signInWithPassword: ReturnType<typeof vi.fn>;
  signOut: ReturnType<typeof vi.fn>;
  signUp: ReturnType<typeof vi.fn>;
};

type AuthValue = ReturnType<typeof useAuth>;

function AuthProbe({ onValue }: { onValue: (value: AuthValue) => void }) {
  const auth = useAuth();
  useEffect(() => onValue(auth), [auth, onValue]);
  return null;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AuthProvider signup", () => {
  it("onboards the ParkSmart profile when signup returns a session", async () => {
    const { ApiError } = await import("@/lib/api");
    const supabase = createSupabaseMock({
      data: {
        user: { id: profile.id },
        session: { access_token: "signup-access-token" },
      },
      error: null,
    });
    mocks.createBrowserSupabaseClient.mockReturnValue(supabase);
    mocks.getCurrentUser.mockRejectedValue(
      new ApiError({
        code: "PROFILE_NOT_FOUND",
        message: "The ParkSmart profile does not exist.",
        status: 403,
      }),
    );
    mocks.onboardCurrentUser.mockResolvedValue(profile);
    let authValue = null as unknown as AuthValue;

    render(
      <AuthProvider>
        <AuthProbe onValue={(value) => { authValue = value; }} />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(mocks.createBrowserSupabaseClient).toHaveBeenCalledOnce(),
    );

    const result = await authValue.signUp({
      fullName: "User",
      email: "user@example.com",
      password: "safe-test-password",
    });

    expect(result).toEqual({
      profile,
      error: null,
      confirmationRequired: false,
    });
    expect(mocks.getCurrentUser).toHaveBeenCalledOnce();
    expect(mocks.onboardCurrentUser).toHaveBeenCalledOnce();
    await waitFor(() => expect(authValue.status).toBe("authenticated"));
    expect(authValue.profile).toEqual(profile);
  });

  it("returns confirmation required without calling the backend when signup has no session", async () => {
    const supabase = createSupabaseMock({
      data: {
        user: { id: profile.id },
        session: null,
      },
      error: null,
    });
    mocks.createBrowserSupabaseClient.mockReturnValue(supabase);
    let authValue = null as unknown as AuthValue;

    render(
      <AuthProvider>
        <AuthProbe onValue={(value) => { authValue = value; }} />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(mocks.createBrowserSupabaseClient).toHaveBeenCalledOnce(),
    );

    const result = await authValue.signUp({
      fullName: "User",
      email: "user@example.com",
      password: "safe-test-password",
    });

    expect(result).toEqual({
      profile: null,
      error: null,
      confirmationRequired: true,
    });
    expect(mocks.getCurrentUser).not.toHaveBeenCalled();
    expect(mocks.onboardCurrentUser).not.toHaveBeenCalled();
    expect(authValue.status).toBe("loading");
  });
});
