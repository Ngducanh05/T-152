import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useWebSpeech } from "./use-web-speech";
import { ApiError, parkSmartApi } from "@/lib/api";

type RecognitionResultInput = {
  isFinal: boolean;
  transcript: string;
};

type RecognitionResultMock = {
  0: { transcript: string };
  isFinal: boolean;
  length: number;
};

class MockSpeechRecognition {
  static instances: MockSpeechRecognition[] = [];
  static available: ((options: {
    langs: string[];
    processLocally: boolean;
    quality: "dictation";
  }) => Promise<"unavailable" | "downloadable" | "available">) | undefined;
  static install: (() => Promise<boolean>) | undefined;

  lang = "";
  continuous = true;
  interimResults = true;
  maxAlternatives = 0;
  processLocally = false;
  onstart: (() => void) | null = null;
  onresult: ((event: { results: RecognitionResultMock[] }) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  start = vi.fn(() => this.onstart?.());
  stop = vi.fn();
  abort = vi.fn();

  constructor() {
    MockSpeechRecognition.instances.push(this);
  }

  emitResults(results: RecognitionResultInput[]) {
    this.onresult?.({
      results: results.map(({ isFinal, transcript }) => ({
        0: { transcript },
        isFinal,
        length: 1,
      })),
    });
  }

  emitError(error: string) {
    this.onerror?.({ error });
  }
}

class MockUtterance {
  static instances: MockUtterance[] = [];

  lang = "";
  voice: SpeechSynthesisVoice | null = null;
  onstart: (() => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(readonly text: string) {
    MockUtterance.instances.push(this);
  }
}

function voice(lang: string, name: string): SpeechSynthesisVoice {
  return {
    default: false,
    lang,
    localService: true,
    name,
    voiceURI: name,
  };
}

class MockSpeechSynthesis {
  voices: SpeechSynthesisVoice[] = [];
  speak = vi.fn((utterance: MockUtterance) => utterance.onstart?.());
  cancel = vi.fn();
  getVoices = vi.fn(() => this.voices);
  private listeners = new Set<() => void>();

  addEventListener(name: string, listener: () => void) {
    if (name === "voiceschanged") this.listeners.add(listener);
  }

  removeEventListener(name: string, listener: () => void) {
    if (name === "voiceschanged") this.listeners.delete(listener);
  }

  emitVoicesChanged() {
    this.listeners.forEach((listener) => listener());
  }
}

class MockMediaRecorder {
  static instances: MockMediaRecorder[] = [];
  static isTypeSupported = vi.fn(() => true);

  state: RecordingState = "inactive";
  mimeType: string;
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onerror: (() => void) | null = null;
  onstop: (() => void) | null = null;
  start = vi.fn(() => {
    this.state = "recording";
  });
  stop = vi.fn(() => {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["voice"], { type: this.mimeType }) });
    this.onstop?.();
  });

  constructor(_stream: MediaStream, options?: MediaRecorderOptions) {
    this.mimeType = options?.mimeType ?? "audio/webm";
    MockMediaRecorder.instances.push(this);
  }
}

function defineWindowProperty(name: string, value: unknown) {
  Object.defineProperty(window, name, {
    configurable: true,
    value,
    writable: true,
  });
}

function installRecognition(kind: "standard" | "webkit") {
  defineWindowProperty(
    kind === "standard" ? "SpeechRecognition" : "webkitSpeechRecognition",
    MockSpeechRecognition,
  );
}

function installSynthesis() {
  const synthesis = new MockSpeechSynthesis();
  defineWindowProperty("speechSynthesis", synthesis);
  defineWindowProperty("SpeechSynthesisUtterance", MockUtterance);
  return synthesis;
}

function installMediaCapture() {
  const stop = vi.fn();
  const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
  const getUserMedia = vi.fn().mockResolvedValue(stream);
  defineWindowProperty("MediaRecorder", MockMediaRecorder);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia },
  });
  return { getUserMedia, stop };
}

beforeEach(() => {
  MockSpeechRecognition.instances = [];
  MockSpeechRecognition.available = undefined;
  MockSpeechRecognition.install = undefined;
  MockUtterance.instances = [];
  MockMediaRecorder.instances = [];
});

afterEach(() => {
  cleanup();
  Reflect.deleteProperty(window, "SpeechRecognition");
  Reflect.deleteProperty(window, "webkitSpeechRecognition");
  Reflect.deleteProperty(window, "speechSynthesis");
  Reflect.deleteProperty(window, "SpeechSynthesisUtterance");
  Reflect.deleteProperty(window, "MediaRecorder");
  Reflect.deleteProperty(navigator, "mediaDevices");
  vi.restoreAllMocks();
});

describe("useWebSpeech", () => {
  it("does not initialize or invoke browser speech APIs when disabled", () => {
    installRecognition("standard");
    const synthesis = installSynthesis();
    const { getUserMedia } = installMediaCapture();
    const { result } = renderHook(() => useWebSpeech(vi.fn(), false));

    act(() => {
      result.current.startListening();
      result.current.speak("Không được đọc");
    });

    expect(result.current.recognitionSupported).toBe(false);
    expect(result.current.synthesisSupported).toBe(false);
    expect(MockSpeechRecognition.instances).toHaveLength(0);
    expect(MockMediaRecorder.instances).toHaveLength(0);
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(synthesis.speak).not.toHaveBeenCalled();
  });

  it("feature-detects unprefixed SpeechRecognition and configures Vietnamese STT", () => {
    installRecognition("standard");
    const { result } = renderHook(() => useWebSpeech(vi.fn()));

    expect(result.current.recognitionSupported).toBe(true);
    const recognition = MockSpeechRecognition.instances[0];
    expect(recognition).toMatchObject({
      lang: "vi-VN",
      continuous: false,
      interimResults: false,
      maxAlternatives: 1,
    });
  });

  it("falls back to webkitSpeechRecognition", () => {
    installRecognition("webkit");
    const { result } = renderHook(() => useWebSpeech(vi.fn()));

    expect(result.current.recognitionSupported).toBe(true);
    expect(MockSpeechRecognition.instances).toHaveLength(1);
  });

  it("prefers on-device Vietnamese recognition when it is available", async () => {
    MockSpeechRecognition.available = vi.fn().mockResolvedValue("available");
    installRecognition("standard");
    const { result } = renderHook(() => useWebSpeech(vi.fn()));
    const recognition = MockSpeechRecognition.instances[0];

    await act(async () => result.current.startListening());

    expect(MockSpeechRecognition.available).toHaveBeenCalledWith({
      langs: ["vi-VN"],
      processLocally: true,
      quality: "dictation",
    });
    expect(recognition.processLocally).toBe(true);
    expect(recognition.start).toHaveBeenCalledOnce();
  });

  it("installs a downloadable Vietnamese language pack before listening", async () => {
    MockSpeechRecognition.available = vi.fn().mockResolvedValue("downloadable");
    MockSpeechRecognition.install = vi.fn().mockResolvedValue(true);
    installRecognition("standard");
    const { result } = renderHook(() => useWebSpeech(vi.fn()));
    const recognition = MockSpeechRecognition.instances[0];

    await act(async () => result.current.startListening());

    expect(MockSpeechRecognition.install).toHaveBeenCalledOnce();
    expect(recognition.processLocally).toBe(true);
    expect(recognition.start).toHaveBeenCalledOnce();
  });

  it("falls back to browser-managed recognition when local Vietnamese is unavailable", async () => {
    MockSpeechRecognition.available = vi.fn().mockResolvedValue("unavailable");
    installRecognition("standard");
    const { result } = renderHook(() => useWebSpeech(vi.fn()));
    const recognition = MockSpeechRecognition.instances[0];

    await act(async () => result.current.startListening());

    expect(recognition.processLocally).toBe(false);
    expect(recognition.start).toHaveBeenCalledOnce();
  });

  it("records a short clip and uses backend transcription when local Vietnamese is unavailable", async () => {
    MockSpeechRecognition.available = vi.fn().mockResolvedValue("unavailable");
    installRecognition("standard");
    const capture = installMediaCapture();
    const transcribe = vi
      .spyOn(parkSmartApi, "transcribeSpeech")
      .mockResolvedValue({ text: "  tìm ô trống khu D  " });
    const onTranscript = vi.fn();
    const { result } = renderHook(() => useWebSpeech(onTranscript));

    await act(async () => result.current.startListening());
    expect(result.current.status).toBe("listening");
    expect(capture.getUserMedia).toHaveBeenCalledOnce();

    await act(async () => {
      result.current.stopListening();
      await Promise.resolve();
    });

    expect(transcribe).toHaveBeenCalledOnce();
    expect(onTranscript).toHaveBeenCalledWith("tìm ô trống khu D");
    expect(capture.stop).toHaveBeenCalledOnce();
    expect(result.current.status).toBe("idle");
  });

  it("shows the backend transcription error code and request reference", async () => {
    MockSpeechRecognition.available = vi.fn().mockResolvedValue("unavailable");
    installRecognition("standard");
    installMediaCapture();
    vi.spyOn(parkSmartApi, "transcribeSpeech").mockRejectedValue(
      new ApiError({
        code: "SPEECH_TRANSCRIPTION_TIMEOUT",
        message: "Speech transcription timed out.",
        requestId: "request-voice-timeout",
        status: 504,
      }),
    );
    const { result } = renderHook(() => useWebSpeech(vi.fn()));

    await act(async () => result.current.startListening());
    await act(async () => {
      result.current.stopListening();
      await Promise.resolve();
    });

    expect(result.current.status).toBe("error");
    expect(result.current.errorMessage).toContain("phản hồi quá chậm");
    expect(result.current.errorMessage).toContain("request-voice-timeout");
  });

  it("reports an unsupported browser without crashing", () => {
    const { result } = renderHook(() => useWebSpeech(vi.fn()));

    expect(result.current.recognitionSupported).toBe(false);
    expect(result.current.synthesisSupported).toBe(false);
    expect(result.current.status).toBe("unsupported");
    expect(() => result.current.startListening()).not.toThrow();
    expect(() => result.current.speak("Xin chào")).not.toThrow();
  });

  it("returns only the trimmed final transcript", () => {
    installRecognition("standard");
    const onTranscript = vi.fn();
    renderHook(() => useWebSpeech(onTranscript));

    act(() => {
      MockSpeechRecognition.instances[0].emitResults([
        { isFinal: true, transcript: "  tìm chỗ đỗ xe  " },
      ]);
    });

    expect(onTranscript).toHaveBeenCalledOnce();
    expect(onTranscript).toHaveBeenCalledWith("tìm chỗ đỗ xe");
  });

  it("ignores interim and blank transcripts", () => {
    installRecognition("standard");
    const onTranscript = vi.fn();
    renderHook(() => useWebSpeech(onTranscript));

    act(() => {
      MockSpeechRecognition.instances[0].emitResults([
        { isFinal: false, transcript: "bản nháp" },
        { isFinal: true, transcript: "   " },
      ]);
    });

    expect(onTranscript).not.toHaveBeenCalled();
  });

  it("maps permission denial to a Vietnamese error", () => {
    installRecognition("standard");
    const { result } = renderHook(() => useWebSpeech(vi.fn()));

    act(() => result.current.startListening());
    act(() => MockSpeechRecognition.instances[0].emitError("not-allowed"));

    expect(result.current.status).toBe("error");
    expect(result.current.errorMessage).toBe(
      "Quyền truy cập microphone đã bị từ chối.",
    );
  });

  it("maps no-speech to a Vietnamese error", () => {
    installRecognition("standard");
    const { result } = renderHook(() => useWebSpeech(vi.fn()));

    act(() => MockSpeechRecognition.instances[0].emitError("no-speech"));

    expect(result.current.status).toBe("error");
    expect(result.current.errorMessage).toBe(
      "Không nghe thấy giọng nói. Vui lòng thử lại.",
    );
  });

  it("does not show an error when the user aborts listening", () => {
    installRecognition("standard");
    const { result } = renderHook(() => useWebSpeech(vi.fn()));
    const recognition = MockSpeechRecognition.instances[0];

    act(() => result.current.startListening());
    act(() => result.current.stopListening());
    act(() => recognition.emitError("aborted"));

    expect(recognition.abort).toHaveBeenCalledOnce();
    expect(result.current.status).toBe("idle");
    expect(result.current.errorMessage).toBeNull();
  });

  it("selects a Vietnamese voice, including voices loaded after mount", () => {
    const synthesis = installSynthesis();
    const { result } = renderHook(() => useWebSpeech(vi.fn()));
    const englishVoice = voice("en-US", "English");
    const vietnamese = voice("vi-VN", "Tiếng Việt");

    synthesis.voices = [englishVoice, vietnamese];
    act(() => synthesis.emitVoicesChanged());
    act(() => result.current.speak("Xin chào"));

    const utterance = MockUtterance.instances[0];
    expect(result.current.synthesisSupported).toBe(true);
    expect(utterance.lang).toBe("vi-VN");
    expect(utterance.voice).toBe(vietnamese);
    expect(synthesis.cancel).toHaveBeenCalledBefore(synthesis.speak);
  });

  it("aborts recognition and cancels speech synthesis on cleanup", () => {
    installRecognition("standard");
    const synthesis = installSynthesis();
    const { result, unmount } = renderHook(() => useWebSpeech(vi.fn()));
    const recognition = MockSpeechRecognition.instances[0];

    act(() => result.current.speak("Hẹn gặp lại"));
    synthesis.cancel.mockClear();
    unmount();

    expect(recognition.abort).toHaveBeenCalledOnce();
    expect(synthesis.cancel).toHaveBeenCalledOnce();
  });
});
