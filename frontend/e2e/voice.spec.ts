import { expect, test, type Page } from "@playwright/test";

import { confirmLocation } from "./helpers";

const THREAD_STORAGE_KEY = "parksmart:agent-thread:USER-001";
const THREAD_ID = "thread-voice-e2e";
const VOICE_TRANSCRIPT = "Tìm ô có sạc gần thang máy";
const AGENT_RESPONSE = "Tôi đã tìm thấy ô F1-D01 phù hợp.";

type RecognitionMode = "final" | "not-allowed";

async function installFakeSpeech(page: Page, mode: RecognitionMode) {
  await page.addInitScript(
    ({ recognitionMode, storageKey, threadId, transcript }) => {
      type RecognitionResult = {
        0: { transcript: string };
        isFinal: boolean;
        length: number;
      };
      type RecognitionResultEvent = { results: RecognitionResult[] };

      class FakeSpeechRecognition {
        lang = "";
        continuous = true;
        interimResults = true;
        maxAlternatives = 0;
        onstart: (() => void) | null = null;
        onresult: ((event: RecognitionResultEvent) => void) | null = null;
        onerror: ((event: { error: string }) => void) | null = null;
        onend: (() => void) | null = null;

        start() {
          this.onstart?.();
          queueMicrotask(() => {
            if (recognitionMode === "not-allowed") {
              this.onerror?.({ error: "not-allowed" });
            } else {
              this.onresult?.({
                results: [
                  {
                    0: { transcript },
                    isFinal: true,
                    length: 1,
                  },
                ],
              });
            }
            this.onend?.();
          });
        }

        stop() {
          this.onend?.();
        }

        abort() {
          this.onend?.();
        }
      }

      class FakeSpeechSynthesisUtterance {
        lang = "";
        voice: SpeechSynthesisVoice | null = null;
        onstart: (() => void) | null = null;
        onend: (() => void) | null = null;
        onerror: (() => void) | null = null;

        constructor(readonly text: string) {}
      }

      const voiceEvents = new Set<() => void>();
      const testState = { spoken: [] as string[], cancelCount: 0 };
      const synthesis = {
        getVoices: () => [
          {
            default: true,
            lang: "vi-VN",
            localService: true,
            name: "Fake Vietnamese",
            voiceURI: "fake-vi-VN",
          },
        ],
        addEventListener: (name: string, listener: () => void) => {
          if (name === "voiceschanged") voiceEvents.add(listener);
        },
        removeEventListener: (name: string, listener: () => void) => {
          if (name === "voiceschanged") voiceEvents.delete(listener);
        },
        speak: (utterance: FakeSpeechSynthesisUtterance) => {
          testState.spoken.push(utterance.text);
          utterance.onstart?.();
        },
        cancel: () => {
          testState.cancelCount += 1;
        },
      };
      const speechWindow = window as Window & {
        SpeechRecognition?: typeof FakeSpeechRecognition;
        SpeechSynthesisUtterance?: typeof FakeSpeechSynthesisUtterance;
        __voiceE2E?: typeof testState;
      };

      Object.defineProperty(speechWindow, "SpeechRecognition", {
        configurable: true,
        value: FakeSpeechRecognition,
      });
      Object.defineProperty(speechWindow, "SpeechSynthesisUtterance", {
        configurable: true,
        value: FakeSpeechSynthesisUtterance,
      });
      Object.defineProperty(speechWindow, "speechSynthesis", {
        configurable: true,
        value: synthesis,
      });
      speechWindow.__voiceE2E = testState;
      sessionStorage.setItem(storageKey, threadId);
    },
    {
      recognitionMode: mode,
      storageKey: THREAD_STORAGE_KEY,
      threadId: THREAD_ID,
      transcript: VOICE_TRANSCRIPT,
    },
  );
}

function successEnvelope(message: string) {
  return {
    success: true,
    data: {
      thread_id: THREAD_ID,
      message,
      intent: null,
      selected_slot: null,
      tool_names: [],
      current_location: "F1-ENTRANCE",
      recommended_slot_ids: [],
      route: null,
    },
    message: null,
  };
}

test("sends a reviewed voice transcript through the existing Agent contract and speaks the response", async ({
  page,
}) => {
  await installFakeSpeech(page, "final");
  let agentCallCount = 0;
  let agentPayload: Record<string, unknown> | null = null;
  await page.route("**/api/v1/agent/chat", async (route) => {
    expect(route.request().method()).toBe("POST");
    agentCallCount += 1;
    agentPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(successEnvelope(AGENT_RESPONSE)),
    });
  });

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Bản đồ đỗ xe trực tiếp" }),
  ).toBeVisible();
  await confirmLocation(page, "F1-ENTRANCE");

  const composer = page.getByRole("textbox", {
    name: "Tin nhắn cho ParkSmart AI",
  });
  await page
    .getByRole("button", { name: "Bắt đầu nhập bằng giọng nói" })
    .click();

  await expect(composer).toHaveValue(VOICE_TRANSCRIPT);
  await expect(
    page.getByText(
      "Đã nhận giọng nói. Hãy kiểm tra nội dung rồi nhấn Gửi.",
    ),
  ).toBeVisible();
  expect(agentCallCount).toBe(0);

  await page.getByRole("button", { name: "Gửi tin nhắn" }).click();
  await expect(page.locator(".message.user")).toContainText(VOICE_TRANSCRIPT);
  await expect(page.locator(".message.agent")).toContainText(AGENT_RESPONSE);

  expect(agentCallCount).toBe(1);
  expect(agentPayload).toEqual({
    thread_id: THREAD_ID,
    user_id: "USER-001",
    vehicle_id: "VEHICLE-001",
    current_location: "F1-ENTRANCE",
    message: VOICE_TRANSCRIPT,
  });
  await expect
    .poll(() =>
      page.evaluate(() => {
        const speechWindow = window as Window & {
          __voiceE2E?: { spoken: string[] };
        };
        return speechWindow.__voiceE2E?.spoken ?? [];
      }),
    )
    .toEqual([AGENT_RESPONSE]);
});

test("shows the permission fallback and keeps the text composer usable", async ({
  page,
}) => {
  await installFakeSpeech(page, "not-allowed");
  const keyboardMessage = "Tôi sẽ nhập yêu cầu bằng bàn phím";
  await page.route("**/api/v1/agent/chat", async (route) => {
    expect(route.request().method()).toBe("POST");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(successEnvelope("Đã nhận yêu cầu nhập bằng chữ.")),
    });
  });

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Bản đồ đỗ xe trực tiếp" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Bắt đầu nhập bằng giọng nói" })
    .click();

  await expect(
    page.getByText("Quyền truy cập microphone đã bị từ chối."),
  ).toBeVisible();
  const composer = page.getByRole("textbox", {
    name: "Tin nhắn cho ParkSmart AI",
  });
  await expect(composer).toBeEnabled();
  await composer.fill(keyboardMessage);
  await page.getByRole("button", { name: "Gửi tin nhắn" }).click();

  await expect(page.locator(".message.user")).toContainText(keyboardMessage);
  await expect(page.locator(".message.agent")).toContainText(
    "Đã nhận yêu cầu nhập bằng chữ.",
  );
  const spoken = await page.evaluate(() => {
    const speechWindow = window as Window & {
      __voiceE2E?: { spoken: string[] };
    };
    return speechWindow.__voiceE2E?.spoken ?? [];
  });
  expect(spoken).toEqual([]);
});
