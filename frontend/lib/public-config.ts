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

export function isRewardsRedemptionEnabled(): boolean {
  return parsePublicBoolean(
    process.env.NEXT_PUBLIC_REWARDS_REDEMPTION_ENABLED,
    false,
  );
}

const MAX_PUBLIC_EMAIL_LENGTH = 254;
const EMAIL_LOCAL_PART_PATTERN = /^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+$/i;
const EMAIL_DOMAIN_LABEL_PATTERN = /^[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?$/i;

export function parsePublicContactEmail(
  value: string | undefined,
): string | null {
  const normalized = value?.trim() ?? "";
  if (!normalized || normalized.length > MAX_PUBLIC_EMAIL_LENGTH) return null;

  const separator = normalized.lastIndexOf("@");
  if (separator <= 0 || separator !== normalized.indexOf("@")) return null;
  const localPart = normalized.slice(0, separator);
  const domain = normalized.slice(separator + 1);
  if (
    localPart.length > 64 ||
    localPart.startsWith(".") ||
    localPart.endsWith(".") ||
    localPart.includes("..") ||
    !EMAIL_LOCAL_PART_PATTERN.test(localPart)
  ) {
    return null;
  }

  const domainLabels = domain.split(".");
  if (
    domainLabels.length < 2 ||
    domainLabels.some((label) => !EMAIL_DOMAIN_LABEL_PATTERN.test(label))
  ) {
    return null;
  }
  return normalized;
}

export function getPrivacyContactEmail(): string | null {
  return parsePublicContactEmail(
    process.env.NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL,
  );
}

export function buildPrivacyContactMailtoUri(
  value: string | undefined,
): string | null {
  const email = parsePublicContactEmail(value);
  if (!email) return null;

  const encodedEmail = encodeURIComponent(email).replace(/%40/gi, "@");
  return `mailto:${encodedEmail}`;
}
