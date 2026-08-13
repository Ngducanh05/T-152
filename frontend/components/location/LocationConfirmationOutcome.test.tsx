import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { activeReservation } from "@/test/fixtures";

import { LocationConfirmationOutcome } from "./LocationConfirmationOutcome";

afterEach(cleanup);

describe("LocationConfirmationOutcome", () => {
  it("shows an explicit parking action only for a matching active reservation", async () => {
    const user = userEvent.setup();
    const onConfirmParking = vi.fn(async () => undefined);
    render(
      <LocationConfirmationOutcome
        locationId="F1-A01"
        activeReservation={activeReservation}
        pending={false}
        onConfirmParking={onConfirmParking}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "Bạn đã xác nhận đang ở F1-A01",
    );
    expect(onConfirmParking).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Xác nhận đã đỗ" }));
    expect(onConfirmParking).toHaveBeenCalledOnce();
  });

  it("only reports the location when there is no active reservation", () => {
    render(
      <LocationConfirmationOutcome
        locationId="F1-D01"
        activeReservation={null}
        pending={false}
        onConfirmParking={vi.fn()}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "Đã cập nhật vị trí hiện tại thành F1-D01",
    );
    expect(screen.queryByRole("button", { name: "Xác nhận đã đỗ" })).not.toBeInTheDocument();
  });

  it("warns for a mismatched reservation and exposes no session action", () => {
    const onConfirmParking = vi.fn();
    render(
      <LocationConfirmationOutcome
        locationId="F1-C03"
        activeReservation={activeReservation}
        pending={false}
        onConfirmParking={onConfirmParking}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "reservation tại F1-A01 nhưng vị trí vừa xác nhận là F1-C03",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Hệ thống chưa xác nhận đỗ xe",
    );
    expect(screen.queryByRole("button", { name: "Xác nhận đã đỗ" })).not.toBeInTheDocument();
    expect(onConfirmParking).not.toHaveBeenCalled();
  });
});
