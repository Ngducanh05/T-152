import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { canonicalMap } from "@/test/fixtures";
import { ApiError } from "@/lib/api";
import type { WrongParkingReport } from "@/lib/types";

import { WrongParkingReportDialog } from "./WrongParkingReportDialog";

afterEach(cleanup);

const createdReport: WrongParkingReport = {
  id: "REPORT-001",
  reporter_user_id: "USER-001",
  slot_id: "F1-D01",
  reason_code: "CROSSED_LINE",
  status: "OPEN",
  observed_plate_number: null,
  description: null,
  created_at: "2026-08-23T10:00:00Z",
  updated_at: "2026-08-23T10:00:00Z",
  resolved_at: null,
  resolved_by: null,
  resolution_note: null,
  verification_outcome: "PENDING",
  reward_points: 20,
  reward_status: "PENDING",
  duplicate_candidate_of_id: null,
  evidence_storage_path: null,
  evidence_content_type: null,
  evidence_size_bytes: null,
  version: 0,
};

describe("WrongParkingReportDialog", () => {
  it("selects a standard reason before submitting normalized optional fields", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => createdReport);
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        rewardPoints={20}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Xe đỗ chéo vạch/ }));
    await user.type(
      screen.getByLabelText("Biển số quan sát được (không bắt buộc)"),
      "51a-123.45",
    );
    await user.type(
      screen.getByLabelText(/Mô tả.*không bắt buộc/),
      "  Xe đỗ chéo sang ô bên cạnh.  ",
    );
    await user.click(screen.getByRole("button", { name: /Gửi báo cáo/ }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledWith({
      slotId: "F1-D01",
      reasonCode: "CROSSED_LINE",
      observedPlateNumber: "51A-123.45",
      description: "Xe đỗ chéo sang ô bên cạnh.",
      evidence: null,
    });
    expect(screen.getByRole("status")).toHaveTextContent("Đã gửi báo cáo");
  });

  it("does not submit a standard reason until the user confirms", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => createdReport);
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        rewardPoints={20}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Ô cần phản ánh"), "F1-A02");
    await user.click(screen.getByRole("button", { name: /Xe chắn lối đi/ }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Biển số quan sát được (không bắt buộc)")).toBeVisible();
    await user.click(screen.getByRole("button", { name: /Gửi báo cáo/ }));
    expect(onSubmit).toHaveBeenCalledWith({
      slotId: "F1-A02",
      reasonCode: "BLOCKING_ACCESS",
      observedPlateNumber: null,
      description: null,
      evidence: null,
    });
  });

  it("passes an optional evidence image without making it required", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => createdReport);
    const evidence = new File(["image-bytes"], "scene.jpg", {
      type: "image/jpeg",
    });
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        rewardPoints={20}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Xe đỗ chéo vạch/ }));
    expect(onSubmit).not.toHaveBeenCalled();
    await user.upload(
      screen.getByLabelText(/^Ảnh hiện trường \(không bắt buộc\)/),
      evidence,
    );
    await user.click(screen.getByRole("button", { name: /Gửi báo cáo/ }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ evidence }),
    );
  });

  it("requires a five-character description only for OTHER", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => createdReport);
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        rewardPoints={20}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Lý do khác" }));
    const submit = screen.getByRole("button", { name: /Gửi báo cáo/ });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText(/Mô tả.*bắt buộc/), "Sai");
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText(/Mô tả.*bắt buộc/), " vị trí");
    expect(submit).toBeEnabled();
  });

  it("guards a standard reason against double submission", async () => {
    const user = userEvent.setup();
    let resolveSubmit!: (report: WrongParkingReport) => void;
    const onSubmit = vi.fn(() => new Promise<WrongParkingReport>((resolve) => { resolveSubmit = resolve; }));
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        rewardPoints={20}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Xe đỗ sai ô/ }));
    const submit = screen.getByRole("button", { name: /Gửi báo cáo/ });
    await user.dblClick(submit);
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(screen.getByRole("status")).toHaveTextContent("đang được gửi");
    resolveSubmit(createdReport);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Đã gửi báo cáo"));
  });

  it("rejects image MIME types outside the exact allowlist", async () => {
    const user = userEvent.setup({ applyAccept: false });
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        rewardPoints={20}
        onClose={vi.fn()}
        onSubmit={vi.fn(async () => createdReport)}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Xe đỗ sai ô/ }));
    await user.upload(
      screen.getByLabelText(/^Ảnh hiện trường/),
      new File(["gif"], "scene.gif", { type: "image/gif" }),
    );

    expect(screen.getByRole("alert")).toHaveTextContent("dung lượng tối đa 5 MB");
    expect(screen.queryByText("Đã chọn: scene.gif")).not.toBeInTheDocument();
  });

  it("rejects evidence larger than five megabytes", async () => {
    const user = userEvent.setup();
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        rewardPoints={20}
        onClose={vi.fn()}
        onSubmit={vi.fn(async () => createdReport)}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Xe đỗ sai ô/ }));
    await user.upload(
      screen.getByLabelText(/^Ảnh hiện trường/),
      new File([new Uint8Array(5_000_001)], "large.jpg", { type: "image/jpeg" }),
    );

    expect(screen.getByRole("alert")).toHaveTextContent("dung lượng tối đa 5 MB");
    expect(screen.queryByText("Đã chọn: large.jpg")).not.toBeInTheDocument();
  });

  it("keeps the complete draft and does not retry after a daily quota error", async () => {
    const user = userEvent.setup();
    const evidence = new File(["jpeg"], "scene.jpg", { type: "image/jpeg" });
    const onSubmit = vi.fn().mockRejectedValue(
      new ApiError({
        code: "REPORT_DAILY_LIMIT_REACHED",
        message: "Daily limit reached.",
        status: 429,
      }),
    );
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        rewardPoints={20}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    const reason = screen.getByRole("button", { name: /Xe đỗ chéo vạch/ });
    await user.click(reason);
    await user.type(screen.getByLabelText(/Mô tả.*không bắt buộc/), "Giữ nguyên bản nháp");
    await user.upload(screen.getByLabelText(/^Ảnh hiện trường/), evidence);
    await user.click(screen.getByRole("button", { name: /Gửi báo cáo/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Bạn đã gửi hết số báo cáo cho hôm nay. Vui lòng thử lại vào ngày mai.",
    );
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(reason).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText(/Mô tả.*không bắt buộc/)).toHaveValue(
      "Giữ nguyên bản nháp",
    );
    expect(screen.getByText("Đã chọn: scene.jpg")).toBeVisible();
    expect(screen.queryByText("Đã gửi báo cáo.")).not.toBeInTheDocument();
  });

  it("renders the evidence privacy notice", async () => {
    const user = userEvent.setup();
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        rewardPoints={20}
        onClose={vi.fn()}
        onSubmit={vi.fn(async () => createdReport)}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Xe đỗ sai ô/ }));

    expect(
      screen.getByText(
        /Ảnh chỉ được dùng để xác minh báo cáo[\s\S]*Admin được ủy quyền/,
      ),
    ).toBeVisible();
    const privacyLink = screen.getByRole("link", {
      name: "Quyền riêng tư (mở trong tab mới)",
    });
    expect(privacyLink).toHaveAttribute("href", "/privacy");
    expect(privacyLink).toHaveAttribute("target", "_blank");
    expect(privacyLink).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("does not close, submit, or reset the draft when the privacy link is activated", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onSubmit = vi.fn(async () => createdReport);
    const evidence = new File(["jpeg"], "draft.jpg", { type: "image/jpeg" });
    render(
      <WrongParkingReportDialog
        slots={canonicalMap.slots}
        initialSlotId="F1-D01"
        rewardPoints={20}
        onClose={onClose}
        onSubmit={onSubmit}
      />,
    );
    const reason = screen.getByRole("button", { name: /Xe đỗ chéo vạch/ });
    await user.click(reason);
    await user.type(screen.getByLabelText(/Mô tả.*không bắt buộc/), "Bản nháp riêng tư");
    await user.upload(screen.getByLabelText(/^Ảnh hiện trường/), evidence);
    const privacyLink = screen.getByRole("link", {
      name: "Quyền riêng tư (mở trong tab mới)",
    });
    expect(privacyLink).toHaveAttribute("href", "/privacy");
    expect(privacyLink).toHaveAttribute("target", "_blank");
    expect(privacyLink).toHaveAttribute("rel", "noopener noreferrer");

    await user.click(privacyLink);

    expect(onClose).not.toHaveBeenCalled();
    expect(onSubmit).not.toHaveBeenCalled();
    expect(reason).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText(/Mô tả.*không bắt buộc/)).toHaveValue(
      "Bản nháp riêng tư",
    );
    const evidenceInput = screen.getByLabelText(
      /^Ảnh hiện trường/,
    ) as HTMLInputElement;
    expect(evidenceInput.files).toHaveLength(1);
    expect(evidenceInput.files?.item(0)).toBe(evidence);
    expect(screen.getByText("Đã chọn: draft.jpg")).toBeVisible();
  });
});
