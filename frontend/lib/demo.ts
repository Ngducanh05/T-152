export const MVP_DEMO_USER_ID = "USER-001";
export const MVP_DEMO_VEHICLE_ID = "VEHICLE-001";

export function createDemoThreadId() {
  return `parksmart-demo-${crypto.randomUUID()}`;
}
