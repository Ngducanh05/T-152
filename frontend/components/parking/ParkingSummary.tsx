import type { ParkingSlot, ParkingStatus } from "@/lib/types";

export interface ParkingSummaryProps {
  status: ParkingStatus;
  slots: ParkingSlot[];
}

export function ParkingSummary({ status, slots }: ParkingSummaryProps) {
  const utilization = status.total
    ? Math.round(((status.reserved + status.occupied) / status.total) * 100)
    : 0;
  const availableEv = slots.filter(
    (slot) => slot.has_charger && slot.status === "AVAILABLE",
  ).length;

  return (
    <div className="stats-row parking-summary" aria-label="Parking status summary">
      <div aria-label="Available slots"><span className="stat-dot available" /><span><b>{status.available}</b><small>Available</small></span></div>
      <div aria-label="Reserved slots"><span className="stat-dot reserved" /><span><b>{status.reserved}</b><small>Reserved</small></span></div>
      <div aria-label="Occupied slots"><span className="stat-dot occupied" /><span><b>{status.occupied}</b><small>Occupied</small></span></div>
      <div aria-label="Available EV slots"><span className="stat-dot ev" /><span><b>{availableEv}</b><small>EV available</small></span></div>
      <div className="occupancy">
        <span><small>Utilization</small><b>{utilization}%</b></span>
        <div aria-hidden="true"><i style={{ width: `${utilization}%` }} /></div>
      </div>
    </div>
  );
}
