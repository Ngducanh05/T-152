import { afterEach, describe, expect, it, vi } from "vitest";

import {
  isAgentEnabled,
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
