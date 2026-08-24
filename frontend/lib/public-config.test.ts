import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildPrivacyContactMailtoUri,
  isAgentEnabled,
  getPrivacyContactEmail,
  parsePublicContactEmail,
  isSpeechEnabled,
  parsePublicBoolean,
} from "./public-config";

afterEach(() => vi.unstubAllEnvs());

describe("public feature configuration", () => {
  it("parses explicit true and false strings without truthy string coercion", () => {
    expect(parsePublicBoolean("true", false)).toBe(true);
    expect(parsePublicBoolean(" FALSE ", true)).toBe(false);
    expect(parsePublicBoolean(undefined, true)).toBe(true);
  });

  it("keeps existing behavior enabled by default and honors public flags", () => {
    expect(isAgentEnabled()).toBe(true);
    expect(isSpeechEnabled()).toBe(true);

    vi.stubEnv("NEXT_PUBLIC_AGENT_ENABLED", "false");
    vi.stubEnv("NEXT_PUBLIC_SPEECH_ENABLED", "false");

    expect(isAgentEnabled()).toBe(false);
    expect(isSpeechEnabled()).toBe(false);
  });
});

describe("public privacy contact", () => {
  it("accepts a valid configured email", () => {
    vi.stubEnv("NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL", "privacy@example.com");
    expect(getPrivacyContactEmail()).toBe("privacy@example.com");
  });

  it("trims surrounding whitespace", () => {
    expect(parsePublicContactEmail("  privacy@example.com \n")).toBe(
      "privacy@example.com",
    );
  });

  it.each([undefined, "", "   "])("returns null for an empty value", (value) => {
    expect(parsePublicContactEmail(value)).toBeNull();
  });

  it.each([
    "not-an-email",
    "missing-domain@",
    "two@@example.com",
    ".privacy@example.com",
    "privacy@example",
  ])("returns null for an invalid email: %s", (value) => {
    expect(parsePublicContactEmail(value)).toBeNull();
  });

  it("returns null when the value is too long", () => {
    expect(
      parsePublicContactEmail(`${"a".repeat(245)}@example.com`),
    ).toBeNull();
  });

  it.each([
    ["privacy@example.com", "mailto:privacy@example.com"],
    [
      "privacy+delete@example.com",
      "mailto:privacy%2Bdelete@example.com",
    ],
  ])("builds a safe mailto URI for %s", (email, expected) => {
    expect(buildPrivacyContactMailtoUri(email)).toBe(expected);
  });

  it.each([undefined, "", "not-an-email"])(
    "does not build a mailto URI for a missing or invalid email",
    (value) => {
      expect(buildPrivacyContactMailtoUri(value)).toBeNull();
    },
  );

  it.each([
    ["privacy?subject=delete@example.com", "%3Fsubject%3Ddelete"],
    ["privacy#delete@example.com", "%23delete"],
  ])("encodes query or fragment characters in %s", (email, encodedPart) => {
    const uri = buildPrivacyContactMailtoUri(email);

    expect(uri).toContain(encodedPart);
    expect(uri?.slice("mailto:".length)).not.toMatch(/[?#]/);
  });
});
