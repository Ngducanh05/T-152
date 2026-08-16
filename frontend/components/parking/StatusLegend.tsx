export function StatusLegend() {
  return (
    <div className="map-legend" aria-label="Chú thích sơ đồ bãi xe">
      <span><i className="available">✓</i>Đang trống</span>
      <span><i className="reserved">R</i>Đã giữ</span>
      <span><i className="occupied">●</i>Đã có xe</span>
      <span><i className="ev">⚡</i>Có sạc điện</span>
      <span><i className="accessible">♿</i>Dễ tiếp cận</span>
      <span><i className="recommended">★</i>Được đề xuất</span>
      <span><i className="location">⌖</i>Vị trí của bạn</span>
      <span><i className="route">━</i>Đường đang xem</span>
    </div>
  );
}
