import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

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
  it("derives quick choices and all slot options from the map without aisles", async () => {
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

    const quickChoices = screen.getByRole("group", { name: "Vị trí nhanh" });
    expect(
      Array.from(quickChoices.querySelectorAll("button"), (button) => button.textContent),
    ).toEqual([
      "F1-ENTRANCE",
      "F1-EXIT",
      "F1-CP1",
      "F1-CP2",
      "F1-CP3",
      "F1-ELEVATOR",
    ]);
    expect(screen.queryByText("F1-A-W")).not.toBeInTheDocument();
    const expectedSlotIds = pickerMap().nodes
      .filter((node) => node.type === "SLOT")
      .map((node) => node.id)
      .toSorted((left, right) => left.localeCompare(right, undefined, { numeric: true }));
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(
      expectedSlotIds,
    );

    const combobox = screen.getByRole("combobox", { name: "Tìm ô đỗ theo ID" });
    await user.type(combobox, "d0");

    expect(screen.getAllByRole("option")).toHaveLength(9);
    expect(screen.getByRole("option", { name: "F1-D01" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "F1-C01" })).not.toBeInTheDocument();
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

  it("normalizes slot casing and whitespace and prevents duplicate submission", async () => {
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

    const combobox = screen.getByRole("combobox", { name: "Tìm ô đỗ theo ID" });
    await user.type(combobox, "  f1-d01  ");
    const submit = screen.getByRole("button", { name: "Xác nhận vị trí ô đỗ" });
    await user.dblClick(submit);

    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onConfirm).toHaveBeenCalledWith("F1-D01");
    expect(submit).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Đang xác nhận F1-D01");

    resolveConfirmation(true);
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  });

  it("supports keyboard navigation in the slot combobox", async () => {
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

    const combobox = screen.getByRole("combobox", { name: "Tìm ô đỗ theo ID" });
    await user.type(combobox, "F1-D0");
    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");

    expect(combobox).toHaveValue("F1-D02");
    await user.keyboard("{Enter}");
    expect(onConfirm).toHaveBeenCalledWith("F1-D02");
  });
});
