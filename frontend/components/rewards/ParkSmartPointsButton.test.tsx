import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ParkSmartPointsButton } from "./ParkSmartPointsButton";

afterEach(cleanup);

describe("ParkSmartPointsButton", () => {
  it("is an accessible header trigger with a capped visual badge", async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    render(<ParkSmartPointsButton points={1234} onOpen={onOpen} />);

    const button = screen.getByRole("button", {
      name: "ParkSmart Points: 1234 điểm",
    });
    expect(button).toHaveClass("points-trigger");
    expect(button).toHaveTextContent("999+");
    expect(button.querySelector("svg")).not.toBeNull();
    expect(button).not.toHaveTextContent("★");
    await user.click(button);
    expect(onOpen).toHaveBeenCalledOnce();
  });
});
