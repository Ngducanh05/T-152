import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ParkSmartPointsButton } from "./ParkSmartPointsButton";

afterEach(cleanup);

describe("ParkSmartPointsButton", () => {
  it("formats the available-only badge and accessible label", () => {
    render(<ParkSmartPointsButton availablePoints={1_234} onClick={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Open ParkSmart Points, 1234 available points" })).toBeVisible();
    expect(screen.getByText("999+")).toBeVisible();
  });
});
