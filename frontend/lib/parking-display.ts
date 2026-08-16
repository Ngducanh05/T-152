import type { ActorType, ParkingEventType, SlotStatus } from "./types";

const LOCATION_NAMES: Record<string, string> = {
  "F1-ENTRANCE": "Cổng vào tầng F1",
  "F1-EXIT": "Lối ra tầng F1",
  "F1-ELEVATOR": "Thang máy tầng F1",
  "F1-CP1": "Điểm kiểm tra số 1",
  "F1-CP2": "Điểm kiểm tra số 2",
};

export function formatParkingLocation(id: string | null | undefined): string {
  if (!id) return "Chưa xác nhận";
  const slot = /^F1-([A-D])(\d{2})$/.exec(id);
  if (slot) return `Ô ${slot[1]}${slot[2]} (${id})`;
  const zoneLane = /^F1-([A-D])-(?:E|W)$/.exec(id);
  if (zoneLane) return `Lối xe khu ${zoneLane[1]} (${id})`;
  const name = LOCATION_NAMES[id];
  return name ? `${name} (${id})` : id;
}

export function formatSlotStatus(status: SlotStatus): string {
  return {
    AVAILABLE: "Đang trống",
    RESERVED: "Đã được giữ",
    OCCUPIED: "Đã có xe",
  }[status];
}

export function formatEventType(eventType: ParkingEventType): string {
  return {
    VEHICLE_ENTERED: "Xe vào bãi",
    SLOT_RESERVED: "Giữ ô",
    RESERVATION_CANCELLED: "Hủy giữ ô",
    RESERVATION_EXPIRED: "Hết thời gian giữ ô",
    VEHICLE_PARKED: "Xe đã đỗ",
    VEHICLE_LEFT_SLOT: "Xe rời ô",
    VEHICLE_EXITED: "Xe rời bãi",
  }[eventType];
}

export function formatActorType(actorType: ActorType): string {
  return {
    USER: "Người dùng",
    SIMULATOR: "Bộ mô phỏng",
    CAMERA: "Thiết bị ghi hình",
    SYSTEM: "Hệ thống",
  }[actorType];
}
