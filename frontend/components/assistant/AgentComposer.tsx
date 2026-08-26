"use client";

import { ChangeEvent, FormEvent, useState } from "react";

import { useWebSpeech } from "@/hooks/use-web-speech";
import { isSpeechEnabled } from "@/lib/public-config";

interface AgentComposerProps {
  onSend: (message: string) => Promise<string | null>;
  threadReady: boolean;
  chatPending: boolean;
}

export function AgentComposer({
  onSend,
  threadReady,
  chatPending,
}: AgentComposerProps) {
  const speechEnabled = isSpeechEnabled();
  const [draft, setDraft] = useState("");
  const [voiceOrigin, setVoiceOrigin] = useState(false);
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const speech = useWebSpeech(
    (finalTranscript) => {
      setDraft(finalTranscript);
      setVoiceOrigin(true);
      setVoiceNotice(
        "Đã nhận giọng nói. Hãy kiểm tra nội dung rồi nhấn Gửi.",
      );
    },
    speechEnabled,
  );
  const pending = chatPending || submitting;

  function updateDraft(event: ChangeEvent<HTMLInputElement>) {
    const nextDraft = event.target.value;
    setDraft(nextDraft);
    if (!nextDraft.trim()) {
      setVoiceOrigin(false);
      setVoiceNotice(null);
    }
  }

  function toggleListening() {
    if (speech.status === "listening" || speech.status === "preparing") {
      speech.stopListening();
      return;
    }
    if (!pending && threadReady && speech.recognitionSupported) {
      speech.startListening();
    }
  }

  async function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || !threadReady || pending) return;

    const shouldSpeakResponse = voiceOrigin;
    if (speech.status === "listening") speech.stopListening();
    setDraft("");
    setVoiceOrigin(false);
    setVoiceNotice(null);
    setSubmitting(true);
    try {
      const responseMessage = await onSend(message);
      if (speechEnabled && shouldSpeakResponse && responseMessage) {
        speech.speak(responseMessage);
      }
    } finally {
      setSubmitting(false);
    }
  }

  let statusMessage = speechEnabled ? voiceNotice : null;
  if (speechEnabled && !speech.recognitionSupported) {
    statusMessage =
      "Trình duyệt không hỗ trợ nhập giọng nói. Hãy nhập nội dung bằng bàn phím.";
  } else if (speechEnabled && speech.errorMessage) {
    statusMessage = speech.errorMessage;
  } else if (speech.status === "listening") {
    statusMessage = "Đang nghe… Nhấn Dừng nghe để kết thúc.";
  } else if (speech.status === "preparing") {
    statusMessage = "Đang chuẩn bị nhận dạng giọng nói trên thiết bị…";
  } else if (speech.status === "speaking") {
    statusMessage = "Đang đọc câu trả lời.";
  }

  return (
    <>
      <form className="chat-input" onSubmit={submitMessage}>
        <input
          value={draft}
          onChange={updateDraft}
          placeholder="Hỏi ParkSmart AI..."
          aria-label="Tin nhắn cho ParkSmart AI"
          disabled={!threadReady || pending}
        />
        {speechEnabled && speech.status === "speaking" && (
          <button
            type="button"
            onClick={speech.stopSpeaking}
            aria-label="Dừng đọc câu trả lời"
          >
            ■
          </button>
        )}
        {speechEnabled && (
          <button
            type="button"
            className={
              speech.status === "listening" || speech.status === "preparing"
                ? "listening"
                : undefined
            }
            onClick={toggleListening}
            disabled={!threadReady || pending || !speech.recognitionSupported}
            aria-label={
              speech.status === "listening" || speech.status === "preparing"
                ? "Dừng nghe"
                : "Bắt đầu nhập bằng giọng nói"
            }
          >
            {speech.status === "listening" || speech.status === "preparing"
              ? "■"
              : "🎤"}
          </button>
        )}
        <button
          type="submit"
          disabled={!threadReady || pending || !draft.trim()}
          aria-label="Gửi tin nhắn"
        >
          {pending ? "…" : "↑"}
        </button>
      </form>
      {statusMessage && (
        <p className="agent-note" role="status" aria-live="polite">
          {statusMessage}
        </p>
      )}
    </>
  );
}
