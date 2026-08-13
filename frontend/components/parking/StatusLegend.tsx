export function StatusLegend() {
  return (
    <div className="map-legend" aria-label="Parking map legend">
      <span><i className="available">✓</i>Available</span>
      <span><i className="reserved">R</i>Reserved</span>
      <span><i className="occupied">●</i>Occupied</span>
      <span><i className="ev">⚡</i>EV charger</span>
      <span><i className="accessible">♿</i>Accessible</span>
      <span><i className="recommended">★</i>Recommended</span>
      <span><i className="location">⌖</i>Your location</span>
      <span><i className="route">━</i>Active route</span>
    </div>
  );
}
