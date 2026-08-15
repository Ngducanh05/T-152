import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useWebSpeech } from "./use-web-speech";

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

  lang = "";
  continuous = true;
  interimResults = true;
  maxAlternatives = 0;
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

beforeEach(() => {
  MockSpeechRecognition.instances = [];
  MockUtterance.instances = [];
});

afterEach(() => {
  cleanup();
  Reflect.deleteProperty(window, "SpeechRecognition");
  Reflect.deleteProperty(window, "webkitSpeechRecognition");
  Reflect.deleteProperty(window, "speechSynthesis");
  Reflect.deleteProperty(window, "SpeechSynthesisUtterance");
});

describe("useWebSpeech", () => {
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
