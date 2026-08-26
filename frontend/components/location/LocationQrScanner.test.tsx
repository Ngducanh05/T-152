import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let decodeCallback: ((result?: { getText: () => string }) => void) | undefined;
const stop = vi.fn();
const trackStop = vi.fn();
const decodeFromConstraints = vi.fn();

vi.mock("@zxing/browser", () => ({
  BrowserQRCodeReader: class {
    decodeFromConstraints = decodeFromConstraints;
  },
}));

import { LocationQrScanner } from "./LocationQrScanner";

beforeEach(() => {
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn() },
  });
  decodeFromConstraints.mockImplementation(async (_constraints, video, callback) => {
    decodeCallback = callback;
    Object.defineProperty(video, "srcObject", {
      configurable: true,
      writable: true,
      value: { getTracks: () => [{ stop: trackStop }] },
    });
    return { stop };
  });
});

afterEach(() => {
  cleanup();
  decodeCallback = undefined;
  vi.clearAllMocks();
});

function renderScanner(overrides: Partial<React.ComponentProps<typeof LocationQrScanner>> = {}) {
  return render(
    <LocationQrScanner
      pending={false}
      onClose={vi.fn()}
      onManualFallback={vi.fn()}
      onScan={vi.fn(async () => true)}
      {...overrides}
    />,
  );
}

describe("LocationQrScanner", () => {
  it("starts the scanner, submits a valid QR once, and stops scanning", async () => {
    const onScan = vi.fn(async () => true);
    renderScanner({ onScan });

    await waitFor(() => expect(decodeFromConstraints).toHaveBeenCalledOnce());
    decodeCallback?.({ getText: () => "parksmart:location:v1:PSLOC-F3-D-W" });
    await waitFor(() => expect(onScan).toHaveBeenCalledWith("parksmart:location:v1:PSLOC-F3-D-W"));
    expect(stop).toHaveBeenCalledOnce();
    expect(trackStop).toHaveBeenCalledOnce();

    decodeCallback?.({ getText: () => "parksmart:location:v1:PSLOC-F3-D-W" });
    expect(onScan).toHaveBeenCalledOnce();
  });

  it("rejects an unrelated QR and releases scanner resources", async () => {
    const onScan = vi.fn(async () => true);
    renderScanner({ onScan });

    await waitFor(() => expect(decodeCallback).toBeDefined());
    decodeCallback?.({ getText: () => "https://evil.example/qr" });

    expect(onScan).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());
    expect(stop).toHaveBeenCalledOnce();
    expect(trackStop).toHaveBeenCalledOnce();
  });

  it("releases the scanner when unmounted", async () => {
    const view = renderScanner();
    await waitFor(() => expect(decodeFromConstraints).toHaveBeenCalledOnce());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Đưa mã QR vào khung hình"));

    view.unmount();

    expect(stop).toHaveBeenCalledOnce();
    expect(trackStop).toHaveBeenCalledOnce();
  });

  it("releases the scanner before closing or opening manual fallback", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onManualFallback = vi.fn();
    const closeView = renderScanner({ onClose });
    await waitFor(() => expect(decodeFromConstraints).toHaveBeenCalledOnce());

    await user.click(screen.getByRole("button", { name: "Đóng quét QR" }));
    expect(stop).toHaveBeenCalledOnce();
    expect(trackStop).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
    closeView.unmount();

    renderScanner({ onManualFallback });
    await waitFor(() => expect(decodeFromConstraints).toHaveBeenCalledTimes(2));
    await user.click(screen.getByRole("button", { name: "Chọn vị trí thủ công" }));
    expect(onManualFallback).toHaveBeenCalledOnce();
    expect(stop).toHaveBeenCalledTimes(2);
    expect(trackStop).toHaveBeenCalledTimes(2);
  });

  it("keeps one scanner across callback rerenders and invokes the newest callback", async () => {
    const firstOnScan = vi.fn(async () => true);
    const newestOnScan = vi.fn(async () => true);
    const view = renderScanner({ onScan: firstOnScan });
    await waitFor(() => expect(decodeFromConstraints).toHaveBeenCalledOnce());

    view.rerender(
      <LocationQrScanner
        pending={false}
        onClose={vi.fn()}
        onManualFallback={vi.fn()}
        onScan={newestOnScan}
      />,
    );

    expect(decodeFromConstraints).toHaveBeenCalledOnce();
    decodeCallback?.({ getText: () => "parksmart:location:v1:PSLOC-F3-D-W" });
    await waitFor(() => expect(newestOnScan).toHaveBeenCalledOnce());
    expect(firstOnScan).not.toHaveBeenCalled();
  });

  it("shows camera initialization failures and retries with a new scanner attempt", async () => {
    const user = userEvent.setup();
    decodeFromConstraints.mockRejectedValueOnce(new Error("permission denied"));
    renderScanner();

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Không thể truy cập camera."));
    await user.click(screen.getByRole("button", { name: "Quét lại" }));
    await waitFor(() => expect(decodeFromConstraints).toHaveBeenCalledTimes(2));
  });
});
