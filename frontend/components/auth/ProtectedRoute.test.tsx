import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AuthenticatedProfile, AuthStatus } from "@/lib/auth";
import { ProtectedRoute } from "./ProtectedRoute";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  useAuth: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace }),
}));
vi.mock("./AuthProvider", () => ({
  useAuth: mocks.useAuth,
}));

function authState(
  status: AuthStatus,
  profile: AuthenticatedProfile | null,
) {
  mocks.useAuth.mockReturnValue({
    status,
    profile,
    initializationError: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
  });
}

const userProfile: AuthenticatedProfile = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "user@example.com",
  full_name: "User",
  role: "user",
  parking_user_id: "USER-101",
  default_vehicle_id: "VEHICLE-101",
};

const adminProfile: AuthenticatedProfile = {
  id: "22222222-2222-4222-8222-222222222222",
  email: "admin@example.com",
  full_name: "Admin",
  role: "admin",
  parking_user_id: null,
  default_vehicle_id: null,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProtectedRoute", () => {
  it("redirects guests to login", async () => {
    authState("guest", null);

    render(
      <ProtectedRoute requiredRole="user">
        <div>secret</div>
      </ProtectedRoute>,
    );

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/login"));
  });

  it("redirects a user away from the admin route", async () => {
    authState("authenticated", userProfile);

    render(
      <ProtectedRoute requiredRole="admin">
        <div>admin dashboard</div>
      </ProtectedRoute>,
    );

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/"));
  });

  it("redirects an admin away from the user route", async () => {
    authState("authenticated", adminProfile);

    render(
      <ProtectedRoute requiredRole="user">
        <div>chat</div>
      </ProtectedRoute>,
    );

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/admin"));
  });

  it("renders only when the authenticated role matches", () => {
    authState("authenticated", userProfile);

    const { getByText } = render(
      <ProtectedRoute requiredRole="user">
        <div>chat</div>
      </ProtectedRoute>,
    );

    expect(getByText("chat")).toBeVisible();
    expect(mocks.replace).not.toHaveBeenCalled();
  });
});
