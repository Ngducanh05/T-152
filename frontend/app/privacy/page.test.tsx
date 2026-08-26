import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PrivacyPage from "./page";

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

describe("PrivacyPage", () => {
  it("renders the complete public-beta report privacy disclosure", () => {
    render(<PrivacyPage />);

    expect(
      screen.getByRole("heading", { name: "Dữ liệu có thể được thu thập" }),
    ).toBeVisible();
    expect(screen.getByText(/Ảnh hiện trường do bạn tùy chọn/)).toBeVisible();
    expect(screen.getByRole("heading", { name: "Mục đích sử dụng" })).toBeVisible();
    expect(screen.getByText(/private Storage bucket/)).toBeVisible();
    expect(screen.getByText(/signed URL có thời hạn/)).toBeVisible();
    expect(
      screen.getByText(
        /Hard-delete xóa bản ghi báo cáo và yêu cầu xóa Storage object tương ứng/,
      ),
    ).toBeVisible();
    expect(
      screen.getByText(/hệ thống ghi cảnh báo.*object còn sót/),
    ).toBeVisible();
    expect(screen.getByText(/Reward ledger có thể được giữ/)).toBeVisible();
    expect(screen.getByText(/không phải hệ thống vận hành bãi xe 24\/7/)).toBeVisible();
  });

  it("creates a mailto link only for a valid configured email", () => {
    vi.stubEnv("NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL", " privacy@example.com ");
    render(<PrivacyPage />);

    expect(
      screen.getByRole("link", { name: "privacy@example.com" }),
    ).toHaveAttribute("href", "mailto:privacy@example.com");
    expect(screen.queryByText("Kênh liên hệ đang được cấu hình")).not.toBeInTheDocument();
  });

  it("shows the normal email while encoding reserved mailto characters", () => {
    vi.stubEnv(
      "NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL",
      "privacy+delete@example.com",
    );
    render(<PrivacyPage />);

    expect(
      screen.getByRole("link", { name: "privacy+delete@example.com" }),
    ).toHaveAttribute("href", "mailto:privacy%2Bdelete@example.com");
  });

  it.each([undefined, "not-an-email"])(
    "shows the safe fallback without a mailto for missing or invalid email",
    (value) => {
      if (value === undefined) {
        vi.stubEnv("NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL", "");
      } else {
        vi.stubEnv("NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL", value);
      }
      render(<PrivacyPage />);

      expect(screen.getByText("Kênh liên hệ đang được cấu hình")).toBeVisible();
      expect(document.querySelector('a[href^="mailto:"]')).toBeNull();
    },
  );
});
