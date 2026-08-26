export interface IdempotencyAttempt {
  fingerprint: string;
  key: string;
}

type IdempotencyAttemptRef = {
  current: IdempotencyAttempt | null;
};

function createIdempotencyKey(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }

  // Idempotency keys require uniqueness, not secrecy.
  return `ps-${Date.now().toString(36)}-${Math.random()
    .toString(36)
    .slice(2)}`;
}

export function getOrCreateIdempotencyKey(
  ref: IdempotencyAttemptRef,
  fingerprint: string,
): string {
  if (ref.current?.fingerprint !== fingerprint) {
    ref.current = {
      fingerprint,
      key: createIdempotencyKey(),
    };
  }

  return ref.current.key;
}

export function clearIdempotencyKey(ref: IdempotencyAttemptRef): void {
  ref.current = null;
}
