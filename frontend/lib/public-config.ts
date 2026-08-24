export function parsePublicBoolean(
  value: string | undefined,
  defaultValue: boolean,
): boolean {
  const normalized = value?.trim().toLowerCase();
  if (normalized === "true") return true;
  if (normalized === "false") return false;
  return defaultValue;
}

export function isAgentEnabled(): boolean {
  return parsePublicBoolean(process.env.NEXT_PUBLIC_AGENT_ENABLED, true);
}

export function isSpeechEnabled(): boolean {
  return parsePublicBoolean(process.env.NEXT_PUBLIC_SPEECH_ENABLED, true);
}
