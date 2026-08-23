import type { ParkingIdentity } from "./auth";

export const MVP_DEMO_USER_ID = "USER-001";
export const MVP_DEMO_VEHICLE_ID = "VEHICLE-001";
export const MVP_DEMO_PARKING_IDENTITY: ParkingIdentity = {
  userId: MVP_DEMO_USER_ID,
  vehicleId: MVP_DEMO_VEHICLE_ID,
};

function threadStorageKey(userId: string) {
  return `parksmart:agent-thread:${userId}`;
}

export const MVP_AGENT_THREAD_STORAGE_KEY = threadStorageKey(MVP_DEMO_USER_ID);

export function createDemoThreadId() {
  return crypto.randomUUID();
}

export function getOrCreateThreadId(
  userId: string,
  storage: Storage = sessionStorage,
) {
  const key = threadStorageKey(userId);
  const existing = storage.getItem(key)?.trim();
  if (existing) return existing;
  return rotateThreadId(userId, storage);
}

export function rotateThreadId(
  userId: string,
  storage: Storage = sessionStorage,
) {
  const threadId = createDemoThreadId();
  storage.setItem(threadStorageKey(userId), threadId);
  return threadId;
}

// Compatibility helpers retained for existing demo tests and scripts.
export function getOrCreateDemoThreadId(storage: Storage = sessionStorage) {
  return getOrCreateThreadId(MVP_DEMO_USER_ID, storage);
}

export function rotateDemoThreadId(storage: Storage = sessionStorage) {
  return rotateThreadId(MVP_DEMO_USER_ID, storage);
}
