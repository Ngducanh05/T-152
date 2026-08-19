import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { canonicalMap } from "@/test/fixtures";

import { WrongParkingReportDialog } from "./WrongParkingReportDialog";

afterEach(cleanup);

describe("WrongParkingReportDialog", () => {
  it("submits a standard reason immediately with normalized optional fields", async () => {
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

    await user.click(screen.getByRole("button", { name: "Thêm thông tin" }));
    await user.type(
      screen.getByLabelText("Biển số quan sát được (không bắt buộc)"),
      "51a-123.45",
    );
    await user.type(
      screen.getByLabelText(/Mô tả.*không bắt buộc/),
      "  Xe đỗ chéo sang ô bên cạnh.  ",
    );
    await user.click(screen.getByRole("button", { name: "Gửi: Xe đỗ chéo vạch" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledWith({
      slotId: "F1-D01",
      reasonCode: "CROSSED_LINE",
      observedPlateNumber: "51A-123.45",
      description: "Xe đỗ chéo sang ô bên cạnh.",
    });
    expect(screen.getByRole("status")).toHaveTextContent("Đã gửi báo cáo");
  });

  it("does not require typing for a standard reason", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => undefined);
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Ô cần phản ánh"), "F1-A02");
    await user.click(screen.getByRole("button", { name: "Gửi: Xe chắn lối đi" }));
    expect(onSubmit).toHaveBeenCalledWith({
      slotId: "F1-A02",
      reasonCode: "BLOCKING_ACCESS",
      observedPlateNumber: null,
      description: null,
    });
  });

  it("requires a five-character description only for OTHER", async () => {
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

    await user.click(screen.getByRole("button", { name: "Lý do khác" }));
    const submit = screen.getByRole("button", { name: "Gửi báo cáo lý do khác" });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText(/Mô tả.*bắt buộc/), "Sai");
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText(/Mô tả.*bắt buộc/), " vị trí");
    expect(submit).toBeEnabled();
  });

  it("guards a standard reason against double submission", async () => {
    const user = userEvent.setup();
    let resolveSubmit!: () => void;
    const onSubmit = vi.fn(() => new Promise<void>((resolve) => { resolveSubmit = resolve; }));
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    const reason = screen.getByRole("button", { name: "Gửi: Xe đỗ sai ô" });
    await user.dblClick(reason);
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(screen.getByRole("status")).toHaveTextContent("đang được gửi");
    resolveSubmit();
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Đã gửi báo cáo"));
  });
});
