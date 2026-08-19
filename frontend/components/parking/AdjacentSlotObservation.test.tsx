import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { canonicalMap } from "@/test/fixtures";

import { AdjacentSlotObservation } from "./AdjacentSlotObservation";

afterEach(cleanup);

describe("AdjacentSlotObservation", () => {
  it("shows the two same-row neighbours and delegates optional observations", async () => {
    const user = userEvent.setup();
    const onObserve = vi.fn(async () => undefined);
    render(
      <AdjacentSlotObservation
        parkedSlotId="F1-D03"
        slots={canonicalMap.slots}
        pendingSlotId={null}
        onObserve={onObserve}
      />,
    );

    expect(screen.getByText("Hai ô bên cạnh thế nào?")).toBeVisible();
    expect(screen.getByText(/Ô D02/)).toBeVisible();
    expect(screen.getByText(/Ô D04/)).toBeVisible();
    expect(screen.queryByText(/Ô D01/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Báo F1-D02 có xe đỗ" }));
    expect(onObserve).toHaveBeenCalledWith("F1-D02", "OCCUPIED");
  });

  it("disables every choice while an observation is pending", () => {
    render(
      <AdjacentSlotObservation
        parkedSlotId="F1-D03"
        slots={canonicalMap.slots}
        pendingSlotId="F1-D02"
        onObserve={vi.fn(async () => undefined)}
      />,
    );

    for (const button of screen.getAllByRole("button")) {
      expect(button).toBeDisabled();
    }
    expect(screen.getByRole("status")).toHaveTextContent("Đang cập nhật");
  });
});
