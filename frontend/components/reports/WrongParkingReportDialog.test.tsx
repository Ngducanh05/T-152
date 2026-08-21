import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { canonicalMap } from "@/test/fixtures";

import { WrongParkingReportDialog } from "./WrongParkingReportDialog";

afterEach(cleanup);

function imageFile() {
  return new File(["image-bytes"], "evidence.png", { type: "image/png" });
}

describe("WrongParkingReportDialog", () => {
  it("submits only after image evidence and explicit submit", async () => {
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

    await user.click(screen.getByRole("button", { name: "Xe do sai o" }));
    expect(onSubmit).not.toHaveBeenCalled();
    await user.upload(screen.getByLabelText("Anh bang chung"), imageFile());
    await user.type(
      screen.getByLabelText("Bien so quan sat duoc (khong bat buoc)"),
      "51a-123.45",
    );
    await user.type(screen.getByLabelText(/Mo ta/), "  Xe do cheo.  ");
    await user.click(screen.getByRole("button", { name: "Gui bao cao" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledWith({
      slotId: "F1-D01",
      reasonCode: "WRONG_SLOT",
      observedPlateNumber: "51A-123.45",
      description: "Xe do cheo.",
      evidence: expect.any(File),
    });
    expect(screen.getByRole("status")).toHaveTextContent("Da gui bao cao");
  });

  it("requires image evidence", async () => {
    const user = userEvent.setup();
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        onClose={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Gui bao cao" })).toBeDisabled();
    await user.upload(screen.getByLabelText("Anh bang chung"), imageFile());
    expect(screen.getByRole("button", { name: "Gui bao cao" })).toBeEnabled();
  });

  it("requires a five-character description only for OTHER", async () => {
    const user = userEvent.setup();
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        onClose={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    await user.upload(screen.getByLabelText("Anh bang chung"), imageFile());
    await user.click(screen.getByRole("button", { name: "Ly do khac" }));
    const submit = screen.getByRole("button", { name: "Gui bao cao" });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText(/Mo ta/), "Sai");
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText(/Mo ta/), " vi tri");
    expect(submit).toBeEnabled();
  });

  it("guards explicit submit against double submission", async () => {
    const user = userEvent.setup();
    let resolveSubmit!: () => void;
    const onSubmit = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveSubmit = resolve;
        }),
    );
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    await user.upload(screen.getByLabelText("Anh bang chung"), imageFile());
    const submit = screen.getByRole("button", { name: "Gui bao cao" });
    await user.dblClick(submit);
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(screen.getByRole("status")).toHaveTextContent("dang duoc gui");
    resolveSubmit();
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Da gui bao cao"),
    );
  });
});
