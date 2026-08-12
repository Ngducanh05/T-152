"use client";

import { type CSSProperties, FormEvent, useMemo, useState } from "react";

type SlotStatus = "AVAILABLE" | "OCCUPIED";
type Slot = {
  id: string;
  zone: "A" | "B" | "C";
  status: SlotStatus;
  type: "STANDARD" | "EV" | "ACCESSIBLE";
  elevator: boolean;
};

type Message = { role: "agent" | "user"; text: string };

const initialSlots: Slot[] = [
  { id: "F1-A01", zone: "A", status: "OCCUPIED", type: "STANDARD", elevator: false },
  { id: "F1-A02", zone: "A", status: "AVAILABLE", type: "STANDARD", elevator: true },
  { id: "F1-A03", zone: "A", status: "AVAILABLE", type: "EV", elevator: true },
  { id: "F1-A04", zone: "A", status: "OCCUPIED", type: "STANDARD", elevator: true },
  { id: "F1-A05", zone: "A", status: "AVAILABLE", type: "ACCESSIBLE", elevator: true },
  { id: "F1-A06", zone: "A", status: "OCCUPIED", type: "STANDARD", elevator: false },
  { id: "F1-B01", zone: "B", status: "AVAILABLE", type: "STANDARD", elevator: false },
  { id: "F1-B02", zone: "B", status: "OCCUPIED", type: "STANDARD", elevator: false },
  { id: "F1-B03", zone: "B", status: "AVAILABLE", type: "EV", elevator: false },
  { id: "F1-B04", zone: "B", status: "AVAILABLE", type: "STANDARD", elevator: false },
  { id: "F1-B05", zone: "B", status: "OCCUPIED", type: "STANDARD", elevator: false },
  { id: "F1-B06", zone: "B", status: "AVAILABLE", type: "STANDARD", elevator: false },
  { id: "F1-C01", zone: "C", status: "OCCUPIED", type: "STANDARD", elevator: false },
  { id: "F1-C02", zone: "C", status: "AVAILABLE", type: "STANDARD", elevator: false },
  { id: "F1-C03", zone: "C", status: "AVAILABLE", type: "EV", elevator: false },
  { id: "F1-C04", zone: "C", status: "OCCUPIED", type: "STANDARD", elevator: false },
  { id: "F1-C05", zone: "C", status: "AVAILABLE", type: "STANDARD", elevator: false },
  { id: "F1-C06", zone: "C", status: "OCCUPIED", type: "STANDARD", elevator: false },
];

const locationIds = ["F1-ENTRANCE", "F1-CP1", "F1-CP2", "F1-CP3", "F1-ELEVATOR"];

const zoneGeometry = {
  A: { leftAisle: 2, rightAisle: 34, targets: [9, 18, 27] },
  B: { leftAisle: 34, rightAisle: 66, targets: [40, 50, 60] },
  C: { leftAisle: 66, rightAisle: 97, targets: [73, 82, 92] },
} as const;

function getWalkingRoute(slot: Slot) {
  const startX = 6;
  const startY = 16;
  const laneY = 49;
  const slotNumber = Number(slot.id.slice(-2));
  const slotColumn = (slotNumber - 1) % 3;
  const slotRow = Math.floor((slotNumber - 1) / 3);
  const geometry = zoneGeometry[slot.zone];
  const targetX = geometry.targets[slotColumn];
  const verticalMeters = (laneY - startY) * 0.82;
  const aisleCandidates = [geometry.leftAisle, geometry.rightAisle].map((aisleX) => ({
    aisleX,
    cost: Math.abs(aisleX - startX) * 1.15 + verticalMeters + Math.abs(targetX - aisleX) * 1.15,
  }));
  const best = aisleCandidates.sort((a, b) => a.cost - b.cost)[0];
  const topDistance = Math.round(Math.abs(best.aisleX - startX) * 1.15);
  const crossDistance = Math.round(Math.abs(targetX - best.aisleX) * 1.15);

  const mobileStartX = 6;
  const mobileStartY = 8;
  const mobileLaneY = 25 + ({ A: 0, B: 1, C: 2 }[slot.zone] * 27);
  const mobileTargetX = [20, 50, 80][slotColumn];
  const mobileAisles = [2, 98].map((aisleX) => ({
    aisleX,
    cost: Math.abs(aisleX - mobileStartX) + (mobileLaneY - mobileStartY) + Math.abs(mobileTargetX - aisleX),
  }));
  const bestMobile = mobileAisles.sort((a, b) => a.cost - b.cost)[0];

  return {
    distance: Math.round(best.cost),
    style: {
      "--route-top-left": `${Math.min(startX, best.aisleX)}%`,
      "--route-top-width": `${Math.abs(best.aisleX - startX)}%`,
      "--route-aisle-x": `${best.aisleX}%`,
      "--route-lane-y": `${laneY}%`,
      "--route-final-left": `${Math.min(targetX, best.aisleX)}%`,
      "--route-final-width": `${Math.abs(targetX - best.aisleX)}%`,
      "--route-target-x": `${targetX}%`,
      "--route-mobile-top-left": `${Math.min(mobileStartX, bestMobile.aisleX)}%`,
      "--route-mobile-top-width": `${Math.abs(bestMobile.aisleX - mobileStartX)}%`,
      "--route-mobile-aisle-x": `${bestMobile.aisleX}%`,
      "--route-mobile-lane-y": `${mobileLaneY}%`,
      "--route-mobile-final-left": `${Math.min(mobileTargetX, bestMobile.aisleX)}%`,
      "--route-mobile-final-width": `${Math.abs(mobileTargetX - bestMobile.aisleX)}%`,
      "--route-mobile-target-x": `${mobileTargetX}%`,
    } as CSSProperties,
    steps: [
      { title: "Theo lối chính từ cổng vào", detail: topDistance > 0 ? `${topDistance} mét` : "Tại điểm bắt đầu" },
      { title: `Rẽ vào lối đi cạnh khu ${slot.zone}`, detail: `${Math.round(verticalMeters)} mét` },
      { title: `Đi theo lối giữa hai dãy tới ô ${slot.id.slice(3)}`, detail: `${crossDistance} mét · ô ở ${slotRow === 0 ? "phía trên" : "phía dưới"}` },
    ],
  };
}

export default function Home() {
  const [slots, setSlots] = useState(initialSlots);
  const [selectedId, setSelectedId] = useState("F1-A03");
  const [view, setView] = useState<"map" | "list">("map");
  const [location, setLocation] = useState(locationIds[0]);
  const [needEv, setNeedEv] = useState(true);
  const [nearElevator, setNearElevator] = useState(true);
  const [showRoute, setShowRoute] = useState(false);
  const [sessionSlot, setSessionSlot] = useState<string | null>(null);
  const [showLocationConfirm, setShowLocationConfirm] = useState(false);
  const [showSimulator, setShowSimulator] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [input, setInput] = useState("");
  const [events, setEvents] = useState([
    "10:42 · F1-B02 chuyển sang OCCUPIED",
    "10:40 · F1-A03 chuyển sang AVAILABLE",
    "10:38 · Đã tải kịch bản demo",
  ]);
  const [messages, setMessages] = useState<Message[]>([
    { role: "agent", text: "Chào Minh! Tôi có thể giúp bạn tìm ô phù hợp, chỉ đường hoặc ghi nhớ vị trí xe." },
  ]);

  const available = slots.filter((slot) => slot.status === "AVAILABLE").length;
  const selected = slots.find((slot) => slot.id === selectedId) ?? slots[0];
  const route = useMemo(() => getWalkingRoute(selected), [selected]);

  const recommendation = useMemo(() => {
    const candidates = slots.filter((slot) => {
      if (slot.status !== "AVAILABLE") return false;
      if (needEv && slot.type !== "EV") return false;
      if (nearElevator && !slot.elevator) return false;
      return true;
    });
    return candidates.sort((a, b) => getWalkingRoute(a).distance - getWalkingRoute(b).distance)[0] ?? null;
  }, [slots, needEv, nearElevator]);
  const recommendationRoute = recommendation ? getWalkingRoute(recommendation) : null;

  function addAgent(text: string) {
    setMessages((current) => [...current, { role: "agent", text }]);
  }

  function handleRecommend() {
    if (!recommendation) {
      addAgent("Hiện không có ô nào đáp ứng đầy đủ tiêu chí. Bạn có thể bỏ yêu cầu gần thang máy hoặc sạc EV.");
      return;
    }
    setSelectedId(recommendation.id);
    setShowRoute(false);
    addAgent(`${recommendation.id} là lựa chọn phù hợp nhất: đang trống${recommendation.type === "EV" ? ", có trạm sạc" : ""}${recommendation.elevator ? ", gần thang máy" : ""} và cách bạn khoảng ${getWalkingRoute(recommendation).distance} m theo lối đi.`);
  }

  function handleRoute() {
    setView("map");
    setShowRoute(true);
    addAgent(`Đã tạo đường đi ngắn nhất đến ${selected.id} bằng Dijkstra trên mạng lưới hành lang. Tổng quãng đường ${route.distance} m.`);
  }

  function confirmParking() {
    if (selected.status !== "AVAILABLE") {
      addAgent(`${selected.id} vừa không còn trống. Tôi sẽ không tạo phiên đỗ xe và có thể đề xuất ô khác cho bạn.`);
      return;
    }
    setSlots((current) => current.map((slot) => slot.id === selected.id ? { ...slot, status: "OCCUPIED" } : slot));
    setSessionSlot(selected.id);
    setShowRoute(false);
    setEvents((current) => [`10:45 · ${selected.id} chuyển sang OCCUPIED`, ...current]);
    addAgent(`Đã ghi nhớ xe 51A-123.45 tại ${selected.id}, tầng 1, khu ${selected.zone}. Phiên đỗ xe đang hoạt động.`);
  }

  function findMyCar() {
    if (!sessionSlot) {
      addAgent("Tôi chưa có thông tin vị trí xe của bạn. Hãy xác nhận ô đỗ bằng ID.");
      return;
    }
    setSelectedId(sessionSlot);
    setShowRoute(true);
    addAgent(`Xe của bạn đang ở ${sessionSlot}. Tôi đã tạo chỉ dẫn từ ${location.toLowerCase()} đến xe.`);
  }

  function completeSession() {
    if (!sessionSlot) return;
    const completed = sessionSlot;
    setSlots((current) => current.map((slot) => slot.id === completed ? { ...slot, status: "AVAILABLE" } : slot));
    setSessionSlot(null);
    setShowRoute(false);
    setEvents((current) => [`10:47 · ${completed} chuyển sang AVAILABLE`, ...current]);
    addAgent(`Đã kết thúc phiên đỗ xe tại ${completed}. Ô đã được trả về trạng thái trống.`);
  }

  function resetDemo() {
    setSlots(initialSlots);
    setSelectedId("F1-A03");
    setSessionSlot(null);
    setShowRoute(false);
    setEvents(["10:48 · Đã đặt lại toàn bộ dữ liệu demo"]);
  }

  function toggleSimulatedSlot(id: string) {
    const target = slots.find((slot) => slot.id === id);
    if (!target || target.id === sessionSlot) return;
    const next: SlotStatus = target.status === "AVAILABLE" ? "OCCUPIED" : "AVAILABLE";
    setSlots((current) => current.map((slot) => slot.id === id ? { ...slot, status: next } : slot));
    setEvents((current) => [`10:46 · ${id} chuyển sang ${next}`, ...current]);
  }

  function sendMessage(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text) return;
    setMessages((current) => [...current, { role: "user", text }]);
    setInput("");
    const normalized = text.toLowerCase();
    setTimeout(() => {
      if (normalized.includes("xe") && (normalized.includes("ở đâu") || normalized.includes("tìm"))) findMyCar();
      else if (normalized.includes("chỉ đường") || normalized.includes("đến ô")) handleRoute();
      else if (normalized.includes("đã đỗ") || normalized.includes("ghi nhớ")) confirmParking();
      else if (normalized.includes("trống") || normalized.includes("sạc") || normalized.includes("thang máy")) handleRecommend();
      else addAgent(`Tôi đã nhận yêu cầu. Hiện bãi còn ${available}/18 ô trống. Bạn muốn tìm ô, chỉ đường hay tìm lại xe?`);
    }, 350);
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">P</span><span>ParkSmart<span className="brand-ai">AI</span></span></div>
        <nav aria-label="Điều hướng chính">
          <button className="nav-item active"><span>⌂</span><b>Tổng quan</b></button>
          <button className="nav-item" onClick={findMyCar}><span>⌖</span><b>Tìm xe</b></button>
          <button className="nav-item" onClick={() => setShowSimulator(true)}><span>◎</span><b>Mô phỏng</b></button>
        </nav>
        <div className="system-card">
          <div className="system-title"><span className="pulse" /> Hệ thống hoạt động</div>
          <p>Parking State Service</p>
          <div className="service-row"><span>API</span><strong>Ổn định</strong></div>
          <div className="service-row"><span>Agent</span><strong>Sẵn sàng</strong></div>
        </div>
        <button className="profile"><span className="avatar" aria-hidden="true">MN</span><span className="profile-copy"><b>Minh Nguyễn</b><small>51A-123.45 · EV</small></span><span className="profile-menu" aria-hidden="true">···</span></button>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">BÃI XE VINCOM CENTER · TẦNG 1</p><h1>Chào buổi sáng, Minh</h1></div>
          <div className="top-actions">
            <button className="location-button" onClick={() => setShowLocationConfirm(true)}><span className="location-icon">⌖</span><span><small>Vị trí của bạn</small><b>{location}</b></span><span>⌄</span></button>
            <button className="icon-button" aria-label="Thông báo">◔<span className="notification-dot" /></button>
          </div>
        </header>

        <div className="content-grid">
          <section className="main-column">
            {sessionSlot && (
              <div className="session-banner">
                <span className="session-icon">P</span>
                <div><small>PHIÊN ĐỖ XE ĐANG HOẠT ĐỘNG</small><b>Xe của bạn ở {sessionSlot}</b></div>
                <button onClick={findMyCar}>Chỉ đường tới xe</button>
                <button className="text-button" onClick={completeSession}>Kết thúc</button>
              </div>
            )}

            <section className="card map-card">
              <div className="card-header">
                <div><h2>Sơ đồ bãi xe</h2><p>Cập nhật vài giây trước · Parking State Service</p></div>
                <div className="segmented"><button className={view === "map" ? "active" : ""} onClick={() => setView("map")}>Sơ đồ</button><button className={view === "list" ? "active" : ""} onClick={() => setView("list")}>Danh sách</button></div>
              </div>

              <div className="stats-row">
                <div><span className="stat-dot available" /><span><b>{available}</b><small>Ô trống</small></span></div>
                <div><span className="stat-dot occupied" /><span><b>{18 - available}</b><small>Đã có xe</small></span></div>
                <div><span className="stat-dot ev" /><span><b>{slots.filter((s) => s.status === "AVAILABLE" && s.type === "EV").length}</b><small>Ô sạc EV</small></span></div>
                <div className="occupancy"><span><small>Công suất sử dụng</small><b>{Math.round(((18 - available) / 18) * 100)}%</b></span><div><i style={{ width: `${((18 - available) / 18) * 100}%` }} /></div></div>
              </div>

              {view === "map" ? (
                <div className="parking-map">
                  <div className="map-label entrance"><span>↓</span>CỔNG VÀO</div>
                  <div className="map-label elevator"><span>↕</span> THANG MÁY</div>
                  <div className="road road-top"><span>HƯỚNG DI CHUYỂN</span><i>→</i></div>
                  <div className="cross-aisles" aria-hidden="true"><i><span>LỐI ĐI</span></i><i><span>LỐI ĐI</span></i></div>
                  <div className="zones">
                    {(["A", "B", "C"] as const).map((zone) => (
                      <div className="zone" key={zone}>
                        <div className="zone-title"><b>KHU {zone}</b><span>{slots.filter((s) => s.zone === zone && s.status === "AVAILABLE").length} ô trống</span></div>
                        <div className="slot-grid">
                          {slots.filter((slot) => slot.zone === zone).map((slot) => (
                            <button key={slot.id} onClick={() => { setSelectedId(slot.id); setShowRoute(false); }} className={`parking-slot ${slot.status.toLowerCase()} ${slot.type.toLowerCase()} ${selectedId === slot.id ? "selected" : ""} ${sessionSlot === slot.id ? "my-car" : ""}`} aria-label={`${slot.id}, ${slot.status}`}>
                              <span className="slot-type">{slot.type === "EV" ? "⚡" : slot.type === "ACCESSIBLE" ? "♿" : slot.status === "OCCUPIED" ? "▰" : ""}</span>
                              <b>{slot.id.slice(3)}</b>
                              {sessionSlot === slot.id && <em>XE CỦA BẠN</em>}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="road road-bottom"><span>CHECKPOINT A</span><i>→</i><span>CHECKPOINT B</span></div>
                  {showRoute && <div className="route-path" style={route.style} aria-label={`Đường đi theo hành lang từ cổng vào đến ô ${selected.id}`}><span className="route-origin">⌖</span><i className="route-horizontal" /><i className="route-vertical" /><i className="route-final" /><span className="route-turn" /><b className="route-destination">{selected.id.slice(3)}</b></div>}
                </div>
              ) : (
                <div className="slot-list">
                  {slots.map((slot) => <button key={slot.id} onClick={() => setSelectedId(slot.id)} className={selectedId === slot.id ? "active" : ""}><b>{slot.id}</b><span>Khu {slot.zone}</span><span>{slot.type === "EV" ? "Sạc EV" : slot.type === "ACCESSIBLE" ? "Tiếp cận" : "Tiêu chuẩn"}</span><em className={slot.status.toLowerCase()}>{slot.status === "AVAILABLE" ? "Trống" : "Đã có xe"}</em></button>)}
                </div>
              )}

              <div className="legend"><span><i className="available" />Trống</span><span><i className="occupied" />Đã có xe</span><span><i className="ev" />Sạc EV</span><span><i className="accessible" />Tiếp cận</span></div>
            </section>

            <div className="lower-grid">
              <section className="card recommend-card">
                <div className="card-header compact"><div><p className="eyebrow green">ĐỀ XUẤT MINH BẠCH</p><h2>Tìm ô phù hợp</h2></div><span className="deterministic">Deterministic scoring</span></div>
                <div className="preference-row">
                  <button className={needEv ? "selected" : ""} onClick={() => setNeedEv(!needEv)}><span>⚡</span><b>Cần sạc EV</b><small>Điều kiện bắt buộc</small></button>
                  <button className={nearElevator ? "selected" : ""} onClick={() => setNearElevator(!nearElevator)}><span>↕</span><b>Gần thang máy</b><small>Ưu tiên mềm</small></button>
                </div>
                <button className="primary-button" onClick={handleRecommend}>Tìm ô tốt nhất <span>→</span></button>
                {recommendation && recommendationRoute && <div className="recommend-result"><div className="score-ring"><b>{recommendation.id.slice(3)}</b><small>92 điểm</small></div><div><strong>Lựa chọn tốt nhất</strong><p>{recommendationRoute.distance} m theo lối đi · {recommendation.type === "EV" ? "Có sạc EV" : "Ô tiêu chuẩn"} · {recommendation.elevator ? "Gần thang máy" : "Khu yên tĩnh"}</p></div></div>}
              </section>

              <section className="card route-card">
                <div className="card-header compact"><div><p className="eyebrow blue">DIJKSTRA · LỐI ĐI HỢP LỆ</p><h2>Đường tới {selected.id.slice(3)}</h2></div><b className="distance">{route.distance} m</b></div>
                <ol className="route-steps">{route.steps.map((step, index) => <li key={step.title}><i>{index + 1}</i><span><b>{step.title}</b><small>{step.detail}</small></span></li>)}</ol>
                <div className="action-row"><button className="secondary-button" onClick={handleRoute}>Hiện đường đi</button><button className="primary-button" onClick={confirmParking}>Xác nhận đã đỗ</button></div>
              </section>
            </div>
          </section>

          <aside className="assistant-card card">
            <div className="assistant-header"><div className="agent-avatar">AI<span className="online" /></div><div><h2>Trợ lý ParkSmart</h2><p><span /> Sẵn sàng hỗ trợ</p></div><button aria-label="Tùy chọn">···</button></div>
            <div className="conversation" aria-live="polite">
              <div className="date-separator"><span />HÔM NAY<span /></div>
              {messages.map((message, index) => <div key={index} className={`message ${message.role}`}><p>{message.text}</p><small>{message.role === "agent" ? "ParkSmart AI" : "Bạn"} · vừa xong</small></div>)}
            </div>
            <div className="quick-actions"><button onClick={handleRecommend}>⚡ Tìm ô có sạc</button><button onClick={findMyCar}>⌖ Xe của tôi ở đâu?</button><button onClick={() => setShowLocationConfirm(true)}>⌖ Xác nhận vị trí</button></div>
            <form className="chat-input" onSubmit={sendMessage}>
              <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Hỏi ParkSmart AI..." aria-label="Tin nhắn cho ParkSmart AI" />
              <button type="button" onClick={() => { setIsListening(!isListening); if (!isListening) setInput("Tìm cho tôi ô có sạc gần thang máy"); }} className={isListening ? "listening" : ""} aria-label="Nhập bằng giọng nói">{isListening ? "■" : "◉"}</button>
              <button type="submit" aria-label="Gửi tin nhắn">↑</button>
            </form>
            <p className="agent-note"><span>✓</span> Agent chỉ điều phối công cụ; dữ liệu do Parking State Service xác thực.</p>
          </aside>
        </div>
      </section>

      {showLocationConfirm && <div className="modal-backdrop" onClick={() => setShowLocationConfirm(false)}><div className="modal" onClick={(event) => event.stopPropagation()}><button className="modal-close" onClick={() => setShowLocationConfirm(false)}>×</button><p className="eyebrow green">XÁC NHẬN VỊ TRÍ</p><h2>Chọn ID vị trí hiện tại</h2><p>ParkSmart sẽ kiểm tra ID trên backend trước khi cập nhật vị trí của bạn.</p><label>ID node<select value={location} onChange={(event) => setLocation(event.target.value)}>{locationIds.map((item) => <option key={item}>{item}</option>)}</select></label><button className="primary-button" onClick={() => { setShowLocationConfirm(false); addAgent(`Đã xác nhận vị trí: ${location}.`); }}>Xác nhận vị trí</button></div></div>}

      {showSimulator && <div className="modal-backdrop" onClick={() => setShowSimulator(false)}><div className="simulator-panel" onClick={(event) => event.stopPropagation()}><div className="sim-header"><div><p className="eyebrow green">PARKING SIMULATOR</p><h2>Điều khiển dữ liệu demo</h2><p>Event được gửi qua Parking State Service.</p></div><button onClick={() => setShowSimulator(false)}>×</button></div><div className="sim-slots">{slots.map((slot) => <button key={slot.id} disabled={sessionSlot === slot.id} onClick={() => toggleSimulatedSlot(slot.id)}><span className={slot.status.toLowerCase()} /><b>{slot.id}</b><small>{slot.status}</small></button>)}</div><button className="secondary-button full" onClick={resetDemo}>↻ Đặt lại kịch bản demo</button><div className="event-log"><h3>Nhật ký sự kiện</h3>{events.map((event, index) => <p key={index}><span />{event}</p>)}</div></div></div>}
    </main>
  );
}
