"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

export type WebSpeechStatus =
  | "idle"
  | "listening"
  | "speaking"
  | "error"
  | "unsupported";

export interface UseWebSpeechResult {
  recognitionSupported: boolean;
  synthesisSupported: boolean;
  status: WebSpeechStatus;
  errorMessage: string | null;
  startListening: () => void;
  stopListening: () => void;
  speak: (text: string) => void;
  stopSpeaking: () => void;
}

interface SpeechRecognitionAlternativeLike {
  transcript: string;
}

interface SpeechRecognitionResultLike {
  readonly isFinal: boolean;
  readonly length: number;
  readonly [index: number]: SpeechRecognitionAlternativeLike;
}

interface SpeechRecognitionResultListLike {
  readonly length: number;
  readonly [index: number]: SpeechRecognitionResultLike;
}

interface SpeechRecognitionEventLike {
  readonly results: SpeechRecognitionResultListLike;
}

interface SpeechRecognitionErrorEventLike {
  readonly error: string;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionLike;
}

type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
  SpeechSynthesisUtterance?: typeof SpeechSynthesisUtterance;
};

const RECOGNITION_ERROR_MESSAGES: Readonly<Record<string, string>> = {
  "not-allowed": "Quyền truy cập microphone đã bị từ chối.",
  "service-not-allowed": "Dịch vụ nhận dạng giọng nói không được phép sử dụng.",
  "no-speech": "Không nghe thấy giọng nói. Vui lòng thử lại.",
  "audio-capture": "Không thể thu âm từ microphone.",
  network: "Lỗi mạng khi nhận dạng giọng nói.",
};

function recognitionErrorMessage(error: string) {
  return (
    RECOGNITION_ERROR_MESSAGES[error] ??
    "Không thể nhận dạng giọng nói. Vui lòng thử lại."
  );
}

function vietnameseVoice(voices: SpeechSynthesisVoice[]) {
  return voices.find((voice) => voice.lang.toLowerCase().startsWith("vi"));
}

function subscribeToSpeechAvailability() {
  return () => undefined;
}

function recognitionAvailable() {
  if (typeof window === "undefined") return false;
  const speechWindow = window as SpeechWindow;
  return Boolean(
    speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition,
  );
}

function synthesisAvailable() {
  if (typeof window === "undefined") return false;
  const speechWindow = window as SpeechWindow;
  return Boolean(
    speechWindow.speechSynthesis && speechWindow.SpeechSynthesisUtterance,
  );
}

function speechUnavailableOnServer() {
  return false;
}

export function useWebSpeech(
  onTranscript: (finalTranscript: string) => void,
): UseWebSpeechResult {
  const recognitionSupported = useSyncExternalStore(
    subscribeToSpeechAvailability,
    recognitionAvailable,
    speechUnavailableOnServer,
  );
  const synthesisSupported = useSyncExternalStore(
    subscribeToSpeechAvailability,
    synthesisAvailable,
    speechUnavailableOnServer,
  );
  const [status, setStatus] = useState<WebSpeechStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const synthesisRef = useRef<SpeechSynthesis | null>(null);
  const currentUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const voicesRef = useRef<SpeechSynthesisVoice[]>([]);
  const userAbortedRef = useRef(false);
  const recognitionErroredRef = useRef(false);
  const onTranscriptRef = useRef(onTranscript);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  useEffect(() => {
    const speechWindow = window as SpeechWindow;
    const Recognition =
      speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
    const synthesis = speechWindow.speechSynthesis;
    const Utterance = speechWindow.SpeechSynthesisUtterance;
    let recognition: SpeechRecognitionLike | null = null;

    if (Recognition) {
      try {
        recognition = new Recognition();
        recognition.lang = "vi-VN";
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        recognition.onstart = () => {
          setStatus("listening");
          setErrorMessage(null);
        };
        recognition.onresult = (event) => {
          const finalParts: string[] = [];
          for (let index = 0; index < event.results.length; index += 1) {
            const result = event.results[index];
            if (result?.isFinal && result.length > 0) {
              const transcript = result[0]?.transcript.trim();
              if (transcript) finalParts.push(transcript);
            }
          }
          const finalTranscript = finalParts.join(" ").trim();
          if (finalTranscript) onTranscriptRef.current(finalTranscript);
        };
        recognition.onerror = (event) => {
          if (event.error === "aborted" && userAbortedRef.current) return;
          recognitionErroredRef.current = true;
          setErrorMessage(recognitionErrorMessage(event.error));
          setStatus("error");
        };
        recognition.onend = () => {
          userAbortedRef.current = false;
          if (!recognitionErroredRef.current) setStatus("idle");
        };
        recognitionRef.current = recognition;
      } catch {}
    }

    const hasSynthesis = Boolean(synthesis && Utterance);
    if (hasSynthesis) {
      synthesisRef.current = synthesis;
      const updateVoices = () => {
        voicesRef.current = synthesis.getVoices();
      };
      updateVoices();
      synthesis.addEventListener("voiceschanged", updateVoices);

      return () => {
        recognitionRef.current = null;
        if (recognition) {
          recognition.onstart = null;
          recognition.onresult = null;
          recognition.onerror = null;
          recognition.onend = null;
          recognition.abort();
        }
        synthesis.removeEventListener("voiceschanged", updateVoices);
        currentUtteranceRef.current = null;
        synthesisRef.current = null;
        synthesis.cancel();
      };
    }

    return () => {
      recognitionRef.current = null;
      if (recognition) {
        recognition.onstart = null;
        recognition.onresult = null;
        recognition.onerror = null;
        recognition.onend = null;
        recognition.abort();
      }
    };
  }, []);

  const startListening = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      setStatus("unsupported");
      setErrorMessage("Trình duyệt không hỗ trợ nhận dạng giọng nói.");
      return;
    }
    userAbortedRef.current = false;
    recognitionErroredRef.current = false;
    setErrorMessage(null);
    try {
      recognition.start();
    } catch {
      recognitionErroredRef.current = true;
      setStatus("error");
      setErrorMessage("Không thể bắt đầu nhận dạng giọng nói.");
    }
  }, []);

  const stopListening = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) return;
    userAbortedRef.current = true;
    recognitionErroredRef.current = false;
    recognition.abort();
    setErrorMessage(null);
    setStatus("idle");
  }, []);

  const speak = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const synthesis = synthesisRef.current;
    const speechWindow = window as SpeechWindow;
    const Utterance = speechWindow.SpeechSynthesisUtterance;
    if (!synthesis || !Utterance) {
      setStatus("unsupported");
      setErrorMessage("Trình duyệt không hỗ trợ đọc văn bản.");
      return;
    }

    currentUtteranceRef.current = null;
    synthesis.cancel();
    const utterance = new Utterance(trimmed);
    utterance.lang = "vi-VN";
    const availableVoices = synthesis.getVoices();
    if (availableVoices.length > 0) voicesRef.current = availableVoices;
    const voice = vietnameseVoice(voicesRef.current);
    if (voice) utterance.voice = voice;
    utterance.onstart = () => {
      if (currentUtteranceRef.current !== utterance) return;
      setErrorMessage(null);
      setStatus("speaking");
    };
    utterance.onend = () => {
      if (currentUtteranceRef.current !== utterance) return;
      currentUtteranceRef.current = null;
      setStatus("idle");
    };
    utterance.onerror = () => {
      if (currentUtteranceRef.current !== utterance) return;
      currentUtteranceRef.current = null;
      setErrorMessage("Không thể đọc nội dung bằng giọng nói.");
      setStatus("error");
    };
    currentUtteranceRef.current = utterance;
    synthesis.speak(utterance);
  }, []);

  const stopSpeaking = useCallback(() => {
    currentUtteranceRef.current = null;
    synthesisRef.current?.cancel();
    setErrorMessage(null);
    setStatus("idle");
  }, []);

  return {
    recognitionSupported,
    synthesisSupported,
    status:
      !recognitionSupported && !synthesisSupported && status === "idle"
        ? "unsupported"
        : status,
    errorMessage,
    startListening,
    stopListening,
    speak,
    stopSpeaking,
  };
}
