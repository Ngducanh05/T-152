import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { canonicalMap } from "@/test/fixtures";

import { WrongParkingReportDialog } from "./WrongParkingReportDialog";

afterEach(cleanup);

describe("WrongParkingReportDialog", () => {
  it("submits a normalized report and shows confirmation", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => undefined);
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    await user.type(
      screen.getByLabelText("Biển số hoặc mã xe quan sát được (không bắt buộc)"),
      "51a-123.45",
    );
    await user.type(
      screen.getByLabelText(/Mô tả tình trạng/),
      "Xe đỗ chéo sang ô bên cạnh.",
    );
    await user.click(screen.getByRole("button", { name: "Gửi báo cáo" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledWith({
      slotId: "F1-D01",
      observedPlateNumber: "51A-123.45",
      description: "Xe đỗ chéo sang ô bên cạnh.",
    });
    expect(screen.getByRole("status")).toHaveTextContent("Đã gửi báo cáo");
  });

  it("keeps submission disabled until the description is meaningful", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => undefined);
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    const submit = screen.getByRole("button", { name: "Gửi báo cáo" });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText(/Mô tả tình trạng/), "Sai");
    expect(submit).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
