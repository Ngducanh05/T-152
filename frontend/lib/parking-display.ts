import type {
  ActorType,
  FloorId,
  ParkingEventType,
  SlotStatus,
  WrongParkingReason,
  WrongParkingReportStatus,
} from "./types";

const FLOOR_NAMES: Record<FloorId, string> = {
  F1: "Tầng 1",
  F2: "Tầng 2",
  F3: "Tầng 3",
};

const LOCATION_NAMES: Record<string, string> = {
  "F1-ENTRANCE": "Cổng vào (F1)",
  "F1-EXIT": "Lối ra (F1)",
  "F1-ELEVATOR": "Thang máy tầng 1",
  "F2-ELEVATOR": "Thang máy tầng 2",
  "F3-ELEVATOR": "Thang máy tầng 3",
  "F1-RAMP": "Đường dốc tầng 1",
  "F2-RAMP": "Đường dốc tầng 2",
  "F3-RAMP": "Đường dốc tầng 3",
  "F1-CP1": "Điểm kiểm tra số 1 (F1)",
  "F1-CP2": "Điểm kiểm tra số 2 (F1)",
  "F1-CP3": "Điểm kiểm tra số 3 (F1)",
  "F2-CP1": "Điểm kiểm tra số 1 (F2)",
  "F2-CP2": "Điểm kiểm tra số 2 (F2)",
  "F2-CP3": "Điểm kiểm tra số 3 (F2)",
  "F3-CP1": "Điểm kiểm tra số 1 (F3)",
  "F3-CP2": "Điểm kiểm tra số 2 (F3)",
  "F3-CP3": "Điểm kiểm tra số 3 (F3)",
};

export function formatFloorName(floorId: FloorId): string {
  return FLOOR_NAMES[floorId] ?? floorId;
}

export function formatParkingLocation(id: string | null | undefined): string {
  if (!id) return "Chưa xác nhận";
  const slot = /^F([1-3])-([A-D])(\d{2})$/.exec(id);
  if (slot) return `Ô ${slot[2]}${slot[3]} — ${FLOOR_NAMES[`F${slot[1]}` as FloorId]} (${id})`;
  const zoneLane = /^F([1-3])-([A-D])-(?:E|W)$/.exec(id);
  if (zoneLane) return `Lối xe khu ${zoneLane[2]} — ${FLOOR_NAMES[`F${zoneLane[1]}` as FloorId]} (${id})`;
  const checkpoint = /^F([1-3])-CP(\d+)$/.exec(id);
  if (checkpoint) return `Điểm kiểm tra số ${checkpoint[2]} — ${FLOOR_NAMES[`F${checkpoint[1]}` as FloorId]} (${id})`;
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

export function formatWrongParkingReason(reason: WrongParkingReason): string {
  return {
    WRONG_SLOT: "Xe đỗ sai ô",
    CROSSED_LINE: "Xe đỗ chéo vạch",
    BLOCKING_ACCESS: "Xe chắn lối đi",
    OCCUPYING_CHARGER: "Xe chiếm chỗ sạc",
    OTHER: "Lý do khác",
  }[reason];
}

export function formatWrongParkingReportStatus(
  status: WrongParkingReportStatus,
): string {
  return status === "OPEN" ? "Đang mở" : "Đã xử lý";
}
