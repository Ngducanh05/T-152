import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentComposer } from "./AgentComposer";

const speechMock = vi.hoisted(() => ({
  onTranscript: null as ((transcript: string) => void) | null,
  recognitionSupported: true,
  synthesisSupported: true,
  status: "idle" as string,
  errorMessage: null as string | null,
  startListening: vi.fn(),
  stopListening: vi.fn(),
  speak: vi.fn(),
  stopSpeaking: vi.fn(),
}));

vi.mock("@/hooks/use-web-speech", () => ({
  useWebSpeech: (onTranscript: (transcript: string) => void) => {
    speechMock.onTranscript = onTranscript;
    return speechMock;
  },
}));

beforeEach(() => {
  speechMock.onTranscript = null;
  speechMock.recognitionSupported = true;
  speechMock.synthesisSupported = true;
  speechMock.status = "idle";
  speechMock.errorMessage = null;
  speechMock.startListening.mockReset();
  speechMock.stopListening.mockReset();
  speechMock.speak.mockReset();
  speechMock.stopSpeaking.mockReset();
});

afterEach(cleanup);

function renderComposer(
  onSend = vi.fn<(message: string) => Promise<string | null>>(),
  options: { threadReady?: boolean; chatPending?: boolean } = {},
) {
  return render(
    <AgentComposer
      onSend={onSend}
      threadReady={options.threadReady ?? true}
      chatPending={options.chatPending ?? false}
    />,
  );
}

describe("AgentComposer", () => {
  it("submits keyboard text without speaking the response", async () => {
    const onSend = vi.fn(async () => "Phản hồi từ Agent");
    const user = userEvent.setup();
    renderComposer(onSend);

    await user.type(
      screen.getByRole("textbox", { name: "Tin nhắn cho ParkSmart AI" }),
      "Tìm chỗ đỗ",
    );
    await user.click(screen.getByRole("button", { name: "Gửi tin nhắn" }));

    await waitFor(() => expect(onSend).toHaveBeenCalledWith("Tìm chỗ đỗ"));
    expect(speechMock.speak).not.toHaveBeenCalled();
  });

  it("puts a final transcript in the editable input without sending it", () => {
    const onSend = vi.fn(async () => null);
    renderComposer(onSend);

    act(() => speechMock.onTranscript?.("Tìm ô có sạc"));

    expect(screen.getByRole("textbox")).toHaveValue("Tìm ô có sạc");
    expect(onSend).not.toHaveBeenCalled();
    expect(
      screen.getByText(
        "Đã nhận giọng nói. Hãy kiểm tra nội dung rồi nhấn Gửi.",
      ),
    ).toBeVisible();
  });

  it("submits an edited voice draft using the final transcript flow", async () => {
    const onSend = vi.fn(async () => null);
    const user = userEvent.setup();
    renderComposer(onSend);

    act(() => speechMock.onTranscript?.("Tìm ô"));
    await user.type(screen.getByRole("textbox"), " có sạc");
    await user.click(screen.getByRole("button", { name: "Gửi tin nhắn" }));

    await waitFor(() => expect(onSend).toHaveBeenCalledWith("Tìm ô có sạc"));
  });

  it("speaks a successful response for a voice-originated draft", async () => {
    const onSend = vi.fn(async () => "Đã tìm thấy ô F1-D01.");
    const user = userEvent.setup();
    renderComposer(onSend);

    act(() => speechMock.onTranscript?.("Tìm ô giúp tôi"));
    await user.click(screen.getByRole("button", { name: "Gửi tin nhắn" }));

    await waitFor(() =>
      expect(speechMock.speak).toHaveBeenCalledWith("Đã tìm thấy ô F1-D01."),
    );
  });

  it("does not speak when a voice request returns null", async () => {
    const onSend = vi.fn(async () => null);
    const user = userEvent.setup();
    renderComposer(onSend);

    act(() => speechMock.onTranscript?.("Tìm ô giúp tôi"));
    await user.click(screen.getByRole("button", { name: "Gửi tin nhắn" }));

    await waitFor(() => expect(onSend).toHaveBeenCalledOnce());
    expect(speechMock.speak).not.toHaveBeenCalled();
  });

  it("keeps text input available when STT is unsupported or fails", async () => {
    speechMock.recognitionSupported = false;
    const user = userEvent.setup();
    const { rerender } = renderComposer();
    const input = screen.getByRole("textbox");

    expect(
      screen.getByText(
        "Trình duyệt không hỗ trợ nhập giọng nói. Hãy nhập nội dung bằng bàn phím.",
      ),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Bắt đầu nhập bằng giọng nói" }),
    ).toBeDisabled();
    await user.type(input, "Nhập bằng bàn phím");
    expect(input).toHaveValue("Nhập bằng bàn phím");

    speechMock.recognitionSupported = true;
    speechMock.status = "error";
    speechMock.errorMessage = "Quyền truy cập microphone đã bị từ chối.";
    rerender(
      <AgentComposer
        onSend={vi.fn(async () => null)}
        threadReady
        chatPending={false}
      />,
    );

    expect(screen.getByRole("textbox")).toBeEnabled();
    expect(
      screen.getByText("Quyền truy cập microphone đã bị từ chối."),
    ).toBeVisible();
  });

  it("does not start listening while chat is pending", async () => {
    const user = userEvent.setup();
    renderComposer(vi.fn(async () => null), { chatPending: true });
    const microphone = screen.getByRole("button", {
      name: "Bắt đầu nhập bằng giọng nói",
    });

    expect(microphone).toBeDisabled();
    await user.click(microphone);
    expect(speechMock.startListening).not.toHaveBeenCalled();
  });
});
