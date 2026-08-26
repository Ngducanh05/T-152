import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let decodeCallback: ((result?: { getText: () => string }) => void) | undefined;
const stop = vi.fn();
const decodeFromConstraints = vi.fn(async (_constraints, _video, callback) => {
  decodeCallback = callback;
  return { stop };
});

vi.mock("@zxing/browser", () => ({
  BrowserQRCodeReader: class {
    decodeFromConstraints = decodeFromConstraints;
  },
}));

import { LocationQrScanner } from "./LocationQrScanner";

afterEach(() => {
  cleanup();
  decodeCallback = undefined;
  stop.mockClear();
  decodeFromConstraints.mockClear();
});

beforeEach(() => {
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn() } });
});

describe("LocationQrScanner", () => {
  it("initializes only when mounted, submits one ParkSmart QR, and stops scanning", async () => {
    const onScan = vi.fn(async () => true);
    render(<LocationQrScanner pending={false} onClose={vi.fn()} onManualFallback={vi.fn()} onScan={onScan} />);
    await waitFor(() => expect(decodeFromConstraints).toHaveBeenCalledOnce());
    decodeCallback?.({ getText: () => "parksmart:location:v1:PSLOC-F3-D-W" });
    await waitFor(() => expect(onScan).toHaveBeenCalledWith("parksmart:location:v1:PSLOC-F3-D-W"));
    expect(stop).toHaveBeenCalledOnce();
    decodeCallback?.({ getText: () => "parksmart:location:v1:PSLOC-F3-D-W" });
    expect(onScan).toHaveBeenCalledOnce();
  });

  it("does not send unrelated QR data and exposes manual fallback", async () => {
    const user = userEvent.setup();
    const onScan = vi.fn(async () => true);
    const onManualFallback = vi.fn();
    render(<LocationQrScanner pending={false} onClose={vi.fn()} onManualFallback={onManualFallback} onScan={onScan} />);
    await waitFor(() => expect(decodeCallback).toBeDefined());
    decodeCallback?.({ getText: () => "https://evil.example/qr" });
    expect(onScan).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());
    await user.click(screen.getByRole("button", { name: "Chọn vị trí thủ công" }));
    expect(onManualFallback).toHaveBeenCalledOnce();
  });
});
