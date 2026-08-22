import type { ParkingSlot, ParkingStatus } from "@/lib/types";

export interface ParkingSummaryProps {
  status: ParkingStatus;
  slots: ParkingSlot[];
}

export function ParkingSummary({ slots }: ParkingSummaryProps) {
  // Compute stats from the (possibly floor-filtered) slots list
  const total = slots.length;
  const available = slots.filter((s) => s.status === "AVAILABLE").length;
  const reserved = slots.filter((s) => s.status === "RESERVED").length;
  const occupied = slots.filter((s) => s.status === "OCCUPIED").length;
  const utilization = total
    ? Math.round(((reserved + occupied) / total) * 100)
    : 0;
  const availableEv = slots.filter(
    (slot) => slot.has_charger && slot.status === "AVAILABLE",
  ).length;

  return (
    <div className="stats-row parking-summary" aria-label="Tóm tắt trạng thái bãi xe">
      <div aria-label="Ô đang trống"><span className="stat-dot available" /><span><b>{available}</b><small>Đang trống</small></span></div>
      <div aria-label="Ô đã được giữ"><span className="stat-dot reserved" /><span><b>{reserved}</b><small>Đã giữ</small></span></div>
      <div aria-label="Ô đã có xe"><span className="stat-dot occupied" /><span><b>{occupied}</b><small>Đã có xe</small></span></div>
      <div aria-label="Ô sạc điện đang trống"><span className="stat-dot ev" /><span><b>{availableEv}</b><small>Có sạc, đang trống</small></span></div>
      <div className="occupancy">
        <span><small>Tỷ lệ sử dụng</small><b>{utilization}%</b></span>
        <div aria-hidden="true"><i style={{ width: `${utilization}%` }} /></div>
      </div>
    </div>
  );
}
