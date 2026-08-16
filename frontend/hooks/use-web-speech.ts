"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import { ApiError, parkSmartApi } from "@/lib/api";

export type WebSpeechStatus =
  | "idle"
  | "preparing"
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
  processLocally?: boolean;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type SpeechRecognitionAvailability =
  | "unavailable"
  | "downloadable"
  | "downloading"
  | "available";

interface SpeechRecognitionOptionsLike {
  langs: string[];
  processLocally: boolean;
  quality: "dictation";
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionLike;
  available?: (
    options: SpeechRecognitionOptionsLike,
  ) => Promise<SpeechRecognitionAvailability>;
  install?: (options: SpeechRecognitionOptionsLike) => Promise<boolean>;
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
  network:
    "Không thể kết nối dịch vụ nhận dạng giọng nói. Bạn vẫn có thể nhập nội dung bằng bàn phím.",
};

const VIETNAMESE_RECOGNITION_OPTIONS: SpeechRecognitionOptionsLike = {
  langs: ["vi-VN"],
  processLocally: true,
  quality: "dictation",
};
const MAX_RECORDING_MS = 10_000;

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
    speechWindow.SpeechRecognition ??
      speechWindow.webkitSpeechRecognition ??
      mediaRecordingAvailable(),
  );
}

function transcriptionErrorMessage(error: unknown) {
  if (!(error instanceof ApiError)) {
    return "Không thể kết nối tới dịch vụ chuyển giọng nói. Bạn vẫn có thể nhập bằng bàn phím.";
  }
  const message =
    {
      SPEECH_AUDIO_INVALID:
        "Bản ghi âm không hợp lệ. Hãy nói lâu hơn một chút rồi thử lại.",
      SPEECH_AUDIO_TOO_LARGE: "Bản ghi âm quá dài. Hãy thử một câu ngắn hơn.",
      SPEECH_NO_TRANSCRIPT:
        "Không phát hiện lời nói trong bản ghi âm. Vui lòng thử lại.",
      SPEECH_TRANSCRIPTION_TIMEOUT:
        "Dịch vụ chuyển giọng nói phản hồi quá chậm. Vui lòng thử lại.",
      SPEECH_TRANSCRIPTION_UNAVAILABLE:
        "Dịch vụ chuyển giọng nói tạm thời không khả dụng. Vui lòng thử lại.",
    }[error.code] ?? "Không thể chuyển giọng nói thành văn bản.";
  const requestReference = error.requestId
    ? ` Mã yêu cầu: ${error.requestId}.`
    : "";
  return `${message}${requestReference}`;
}

function mediaRecordingAvailable() {
  return Boolean(
    typeof navigator !== "undefined" &&
      typeof navigator.mediaDevices?.getUserMedia === "function" &&
      typeof MediaRecorder !== "undefined",
  );
}

function stopMediaStream(stream: MediaStream | null) {
  stream?.getTracks().forEach((track) => track.stop());
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
  const recognitionConstructorRef =
    useRef<SpeechRecognitionConstructor | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const transcriptionAbortRef = useRef<AbortController | null>(null);
  const discardRecordingRef = useRef(false);
  const synthesisRef = useRef<SpeechSynthesis | null>(null);
  const currentUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const voicesRef = useRef<SpeechSynthesisVoice[]>([]);
  const userAbortedRef = useRef(false);
  const recognitionErroredRef = useRef(false);
  const recognitionAttemptRef = useRef(0);
  const mountedRef = useRef(true);
  const onTranscriptRef = useRef(onTranscript);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  useEffect(() => {
    mountedRef.current = true;
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
        recognitionConstructorRef.current = Recognition;
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
        mountedRef.current = false;
        recognitionAttemptRef.current += 1;
        recognitionRef.current = null;
        recognitionConstructorRef.current = null;
        discardRecordingRef.current = true;
        transcriptionAbortRef.current?.abort();
        transcriptionAbortRef.current = null;
        if (recordingTimerRef.current) clearTimeout(recordingTimerRef.current);
        recordingTimerRef.current = null;
        const recorder = mediaRecorderRef.current;
        mediaRecorderRef.current = null;
        if (recorder?.state !== "inactive") recorder?.stop();
        stopMediaStream(mediaStreamRef.current);
        mediaStreamRef.current = null;
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
      mountedRef.current = false;
      recognitionAttemptRef.current += 1;
      recognitionRef.current = null;
      recognitionConstructorRef.current = null;
      discardRecordingRef.current = true;
      transcriptionAbortRef.current?.abort();
      transcriptionAbortRef.current = null;
      if (recordingTimerRef.current) clearTimeout(recordingTimerRef.current);
      recordingTimerRef.current = null;
      const recorder = mediaRecorderRef.current;
      mediaRecorderRef.current = null;
      if (recorder?.state !== "inactive") recorder?.stop();
      stopMediaStream(mediaStreamRef.current);
      mediaStreamRef.current = null;
      if (recognition) {
        recognition.onstart = null;
        recognition.onresult = null;
        recognition.onerror = null;
        recognition.onend = null;
        recognition.abort();
      }
    };
  }, []);

  const startServerRecording = useCallback(async (attempt: number) => {
    if (!mediaRecordingAvailable()) return false;

    setStatus("preparing");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          autoGainControl: true,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      if (
        !mountedRef.current ||
        recognitionAttemptRef.current !== attempt ||
        userAbortedRef.current
      ) {
        stopMediaStream(stream);
        return true;
      }

      const preferredType = "audio/webm;codecs=opus";
      const recorder = MediaRecorder.isTypeSupported(preferredType)
        ? new MediaRecorder(stream, { mimeType: preferredType })
        : new MediaRecorder(stream);
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      discardRecordingRef.current = false;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        stopMediaStream(mediaStreamRef.current);
        mediaStreamRef.current = null;
        mediaRecorderRef.current = null;
        setErrorMessage("Không thể thu âm từ microphone.");
        setStatus("error");
      };
      recorder.onstop = () => {
        if (recordingTimerRef.current) clearTimeout(recordingTimerRef.current);
        recordingTimerRef.current = null;
        mediaRecorderRef.current = null;
        stopMediaStream(mediaStreamRef.current);
        mediaStreamRef.current = null;
        if (!mountedRef.current || discardRecordingRef.current) return;

        const mimeType = recorder.mimeType || "audio/webm";
        const audio = new Blob(audioChunksRef.current, { type: mimeType });
        audioChunksRef.current = [];
        if (audio.size === 0) {
          setErrorMessage("Không nghe thấy giọng nói. Vui lòng thử lại.");
          setStatus("error");
          return;
        }

        const controller = new AbortController();
        transcriptionAbortRef.current = controller;
        setStatus("preparing");
        void parkSmartApi
          .transcribeSpeech(audio, controller.signal)
          .then(({ text }) => {
            if (!mountedRef.current || controller.signal.aborted) return;
            const transcript = text.trim();
            if (transcript) onTranscriptRef.current(transcript);
            setErrorMessage(null);
            setStatus("idle");
          })
          .catch((error: unknown) => {
            if (!mountedRef.current || controller.signal.aborted) return;
            setErrorMessage(transcriptionErrorMessage(error));
            setStatus("error");
          })
          .finally(() => {
            if (transcriptionAbortRef.current === controller) {
              transcriptionAbortRef.current = null;
            }
          });
      };

      recorder.start();
      setErrorMessage(null);
      setStatus("listening");
      recordingTimerRef.current = setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, MAX_RECORDING_MS);
      return true;
    } catch (error) {
      const permissionDenied =
        error instanceof DOMException && error.name === "NotAllowedError";
      setErrorMessage(
        permissionDenied
          ? "Quyền truy cập microphone đã bị từ chối."
          : "Không thể thu âm từ microphone.",
      );
      setStatus("error");
      return true;
    }
  }, []);

  const startListening = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition && !mediaRecordingAvailable()) {
      setStatus("unsupported");
      setErrorMessage("Trình duyệt không hỗ trợ nhận dạng giọng nói.");
      return;
    }
    userAbortedRef.current = false;
    recognitionErroredRef.current = false;
    setErrorMessage(null);

    const attempt = recognitionAttemptRef.current + 1;
    recognitionAttemptRef.current = attempt;
    const startRecognition = () => {
      if (!recognition) return;
      if (
        !mountedRef.current ||
        recognitionAttemptRef.current !== attempt ||
        userAbortedRef.current
      ) {
        return;
      }
      try {
        recognition.start();
      } catch {
        recognitionErroredRef.current = true;
        setStatus("error");
        setErrorMessage("Không thể bắt đầu nhận dạng giọng nói.");
      }
    };

    const Recognition = recognitionConstructorRef.current;
    setStatus("preparing");
    void (async () => {
      if (!(recognition && "processLocally" in recognition && Recognition?.available)) {
        if (!(await startServerRecording(attempt))) startRecognition();
        return;
      }
      try {
        let availability = await Recognition.available?.(
          VIETNAMESE_RECOGNITION_OPTIONS,
        );
        if (
          (availability === "downloadable" ||
            availability === "downloading") &&
          Recognition.install
        ) {
          const installed = await Recognition.install(
            VIETNAMESE_RECOGNITION_OPTIONS,
          );
          availability = installed ? "available" : "unavailable";
        }
        recognition.processLocally = availability === "available";
        if (availability !== "available") {
          if (!(await startServerRecording(attempt))) startRecognition();
          return;
        }
      } catch {
        recognition.processLocally = false;
        if (await startServerRecording(attempt)) return;
      }
      startRecognition();
    })();
  }, [startServerRecording]);

  const stopListening = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder?.state === "recording") {
      if (recordingTimerRef.current) clearTimeout(recordingTimerRef.current);
      recordingTimerRef.current = null;
      recorder.stop();
      setStatus("preparing");
      return;
    }

    const recognition = recognitionRef.current;
    userAbortedRef.current = true;
    recognitionAttemptRef.current += 1;
    recognitionErroredRef.current = false;
    transcriptionAbortRef.current?.abort();
    transcriptionAbortRef.current = null;
    discardRecordingRef.current = true;
    if (recognition) recognition.abort();
    stopMediaStream(mediaStreamRef.current);
    mediaStreamRef.current = null;
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
