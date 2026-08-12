export const MVP_DEMO_USER_ID = "USER-001";
export const MVP_DEMO_VEHICLE_ID = "VEHICLE-001";
export const MVP_AGENT_THREAD_STORAGE_KEY =
  `parksmart:agent-thread:${MVP_DEMO_USER_ID}`;

export function createDemoThreadId() {
  return crypto.randomUUID();
}

export function getOrCreateDemoThreadId(storage: Storage = sessionStorage) {
  const existing = storage.getItem(MVP_AGENT_THREAD_STORAGE_KEY)?.trim();
  if (existing) return existing;
  return rotateDemoThreadId(storage);
}

export function rotateDemoThreadId(storage: Storage = sessionStorage) {
  const threadId = createDemoThreadId();
  storage.setItem(MVP_AGENT_THREAD_STORAGE_KEY, threadId);
  return threadId;
}
