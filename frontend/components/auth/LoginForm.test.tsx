import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "./LoginForm";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  refresh: vi.fn(),
  useAuth: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }),
}));
vi.mock("./AuthProvider", () => ({
  useAuth: mocks.useAuth,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("LoginForm", () => {
  it("shows a safe error for invalid credentials and never asks for a role", async () => {
    const signIn = vi.fn(async () => ({
      profile: null,
      error: "Email hoặc mật khẩu không đúng.",
    }));
    mocks.useAuth.mockReturnValue({
      status: "guest",
      profile: null,
      initializationError: null,
      signIn,
      signUp: vi.fn(),
      signOut: vi.fn(),
    });
    const user = userEvent.setup();

    render(<LoginForm />);
    await user.type(screen.getByLabelText("Email"), "wrong@example.com");
    await user.type(screen.getByLabelText("Mật khẩu"), "not-the-password");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Email hoặc mật khẩu không đúng.",
    );
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(signIn).toHaveBeenCalledWith("wrong@example.com", "not-the-password");
  });

  it("routes a successful user login to the user application", async () => {
    const signIn = vi.fn(async () => ({
      profile: {
        id: "11111111-1111-4111-8111-111111111111",
        email: "user@example.com",
        full_name: "User",
        role: "user" as const,
        parking_user_id: "USER-101",
        default_vehicle_id: "VEHICLE-101",
      },
      error: null,
    }));
    mocks.useAuth.mockReturnValue({
      status: "guest",
      profile: null,
      initializationError: null,
      signIn,
      signUp: vi.fn(),
      signOut: vi.fn(),
    });
    const user = userEvent.setup();

    render(<LoginForm />);
    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Mật khẩu"), "safe-test-password");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/"));
  });

  it("routes an already authenticated admin away from login", async () => {
    mocks.useAuth.mockReturnValue({
      status: "authenticated",
      profile: {
        id: "22222222-2222-4222-8222-222222222222",
        email: "admin@example.com",
        full_name: "Admin",
        role: "admin",
        parking_user_id: null,
        default_vehicle_id: null,
      },
      initializationError: null,
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    });

    render(<LoginForm />);

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/admin"));
  });

  it("can open in registration mode by default without a role selector", () => {
    mocks.useAuth.mockReturnValue({
      status: "guest",
      profile: null,
      initializationError: null,
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    });

    render(<LoginForm initialMode="register" />);

    expect(screen.getByLabelText("Họ tên")).toBeVisible();
    expect(screen.getByLabelText("Xác nhận mật khẩu")).toBeVisible();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it.each([
    ["login" as const, "Đăng nhập ParkSmart"],
    ["register" as const, "Đăng ký ParkSmart"],
  ])("shows the privacy link in %s mode", (initialMode, heading) => {
    mocks.useAuth.mockReturnValue({
      status: "guest",
      profile: null,
      initializationError: null,
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    });

    render(<LoginForm initialMode={initialMode} />);

    expect(screen.getByRole("heading", { name: heading })).toBeVisible();
    expect(screen.getByRole("link", { name: "Quyền riêng tư" })).toHaveAttribute(
      "href",
      "/privacy",
    );
  });
});
