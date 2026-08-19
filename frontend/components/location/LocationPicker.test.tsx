import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { formatParkingLocation } from "@/lib/parking-display";
import { canonicalMap } from "@/test/fixtures";

import { LocationPicker } from "./LocationPicker";

afterEach(cleanup);

function pickerMap() {
  return {
    ...canonicalMap,
    nodes: [
      ...canonicalMap.nodes,
      { id: "F1-EXIT", floor_id: "F1" as const, type: "EXIT" as const, x: 100, y: 50 },
      { id: "F1-CP2", floor_id: "F1" as const, type: "CHECKPOINT" as const, x: 50, y: 50 },
      { id: "F1-CP3", floor_id: "F1" as const, type: "CHECKPOINT" as const, x: 85, y: 50 },
      { id: "F1-ELEVATOR", floor_id: "F1" as const, type: "ELEVATOR" as const, x: 50, y: 92 },
    ],
  };
}

describe("LocationPicker", () => {
  it("shows Vietnamese special locations and a tap-only zone/slot flow", async () => {
    const user = userEvent.setup();
    render(
      <LocationPicker
        map={pickerMap()}
        currentLocationId="F1-ENTRANCE"
        pending={false}
        onClose={vi.fn()}
        onConfirm={vi.fn(async () => true)}
      />,
    );

    const quickChoices = screen.getByRole("group", { name: "Địa điểm đặc biệt" });
    expect(
      Array.from(
        quickChoices.querySelectorAll("button"),
        (button) => button.querySelector("b")?.textContent,
      ),
    ).toEqual(
      ["F1-ENTRANCE", "F1-EXIT", "F1-CP1", "F1-CP2", "F1-CP3", "F1-ELEVATOR"].map(
        formatParkingLocation,
      ),
    );
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Tôi đang cạnh một ô đỗ" }));
    await user.click(screen.getByRole("button", { name: "Khu D" }));
    expect(screen.getByRole("group", { name: "Chọn ô khu D" })).toBeVisible();
    expect(screen.getAllByRole("button", { name: /Chọn ô \d{2} khu D/ })).toHaveLength(10);
  });

  it("shows a backend validation code and request ID inside the open picker", () => {
    render(
      <LocationPicker
        map={pickerMap()}
        currentLocationId="F1-ENTRANCE"
        pending={false}
        errorMessage="Không thể hoàn tất yêu cầu. Mã lỗi: LOCATION_NODE_NOT_FOUND. Mã yêu cầu: request-location-404."
        onClose={vi.fn()}
        onConfirm={vi.fn(async () => false)}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("LOCATION_NODE_NOT_FOUND");
    expect(screen.getByRole("alert")).toHaveTextContent("request-location-404");
  });

  it("sends the canonical slot ID and prevents duplicate submission", async () => {
    const user = userEvent.setup();
    let resolveConfirmation!: (success: boolean) => void;
    const onConfirm = vi.fn(
      () => new Promise<boolean>((resolve) => { resolveConfirmation = resolve; }),
    );
    const onClose = vi.fn();
    render(
      <LocationPicker
        map={pickerMap()}
        currentLocationId="F1-ENTRANCE"
        pending={false}
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Tôi đang cạnh một ô đỗ" }));
    await user.click(screen.getByRole("button", { name: "Khu D" }));
    const slot = screen.getByRole("button", { name: "Chọn ô 01 khu D" });
    await user.dblClick(slot);

    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onConfirm).toHaveBeenCalledWith("F1-D01");
    expect(slot).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Đang xác nhận Ô D01 (F1-D01)");

    resolveConfirmation(true);
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  });

  it.each([
    ["A", "01", "F1-A01"],
    ["B", "10", "F1-B10"],
    ["C", "01", "F1-C01"],
    ["D", "10", "F1-D10"],
  ])("builds canonical IDs for zone %s slot %s", async (zone, slot, expectedId) => {
    const user = userEvent.setup();
    const onConfirm = vi.fn(async () => false);
    render(
      <LocationPicker
        map={pickerMap()}
        currentLocationId="F1-ENTRANCE"
        pending={false}
        onClose={vi.fn()}
        onConfirm={onConfirm}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Tôi đang cạnh một ô đỗ" }));
    await user.click(screen.getByRole("button", { name: `Khu ${zone}` }));
    await user.click(screen.getByRole("button", { name: `Chọn ô ${slot} khu ${zone}` }));

    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onConfirm).toHaveBeenCalledWith(expectedId);
  });

  it("confirms a special location without selecting or confirming a parking slot", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn(async () => false);
    render(
      <LocationPicker
        map={pickerMap()}
        currentLocationId={null}
        pending={false}
        onClose={vi.fn()}
        onConfirm={onConfirm}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: formatParkingLocation("F1-CP3") }),
    );
    expect(onConfirm).toHaveBeenCalledWith("F1-CP3");
  });
});
