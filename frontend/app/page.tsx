"use client";

import { FormEvent, useMemo, useState } from "react";

import { ParkingMap } from "@/components/parking/ParkingMap";
import { DEMO_USER_ID, useParkSmartData } from "@/hooks/use-parksmart-data";
import { ApiError, parkSmartApi } from "@/lib/api";
import type { FloorScopedId, RouteResult } from "@/lib/types";

const DEMO_VEHICLE_ID = "VEHICLE-001";
const AGENT_THREAD_ID = "FRONTEND-DEMO-001";

type Message = { role: "agent" | "user"; text: string };

function errorMessage(error: unknown) {
  return error instanceof ApiError
    ? `${error.code}: ${error.message}`
    : "Không thể kết nối tới ParkSmart API.";
}

export default function Home() {
  const data = useParkSmartData();
  const [selectedSlotId, setSelectedSlotId] = useState<FloorScopedId | null>(null);
  const [recommendedSlotIds, setRecommendedSlotIds] = useState<FloorScopedId[]>([]);
  const [activeRoute, setActiveRoute] = useState<RouteResult | null>(null);
  const [confirmedLocationId, setConfirmedLocationId] = useState<FloorScopedId | null>(null);
  const [needEv, setNeedEv] = useState(true);
  const [nearElevator, setNearElevator] = useState(true);
  const [showLocationConfirm, setShowLocationConfirm] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "agent",
      text: "Chào Minh! Bản đồ này dùng dữ liệu trực tiếp từ Parking State Service.",
    },
  ]);

  const currentLocationId =
    confirmedLocationId ?? data.currentLocation?.node_id ?? null;
  const selectableLocations = useMemo(
    () =>
      data.map?.nodes.filter((node) => node.type !== "AISLE") ?? [],
    [data.map],
  );
  const selectedSlot = data.slots.find((slot) => slot.id === selectedSlotId) ?? null;

  async function recommendParking() {
    if (!currentLocationId) {
      setActionError("Hãy xác nhận vị trí hiện tại trước khi tìm ô.");
      return;
    }
    setPending("recommend");
    setActionError(null);
    try {
      const result = await parkSmartApi.recommend({
        user_id: DEMO_USER_ID,
        start_node_id: currentLocationId,
        charging_required: needEv,
        near_elevator: nearElevator,
        limit: 3,
      });
      const ids = result.recommendations.map((candidate) => candidate.slot_id);
      setRecommendedSlotIds(ids);
      setSelectedSlotId(ids[0] ?? null);
      setActiveRoute(null);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  async function requestRoute() {
    if (!currentLocationId || !selectedSlotId) {
      setActionError("Chọn vị trí hiện tại và ô đích để yêu cầu chỉ đường.");
      return;
    }
    setPending("route");
    setActionError(null);
    try {
      const route = await parkSmartApi.getRoute({
        start_node_id: currentLocationId,
        destination_node_id: selectedSlotId,
      });
      setActiveRoute(route);
    } catch (error) {
      setActiveRoute(null);
      setActionError(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  async function confirmLocation(nodeId: FloorScopedId) {
    setPending("location");
    setActionError(null);
    try {
      const location = await parkSmartApi.confirmLocation({
        user_id: DEMO_USER_ID,
        node_id: nodeId,
      });
      setConfirmedLocationId(location.node_id);
      setActiveRoute(null);
      setShowLocationConfirm(false);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  async function resetDemo() {
    setPending("reset");
    setActionError(null);
    try {
      await parkSmartApi.resetDemo();
      setRecommendedSlotIds([]);
      setSelectedSlotId(null);
      setActiveRoute(null);
      setMessages((current) => [
        ...current,
        { role: "agent", text: "Đã gửi yêu cầu đặt lại demo. Bản đồ sẽ cập nhật qua polling." },
      ]);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || pending === "chat") return;
    setInput("");
    setMessages((current) => [...current, { role: "user", text }]);
    setPending("chat");
    setActionError(null);
    try {
      const response = await parkSmartApi.chat({
        thread_id: AGENT_THREAD_ID,
        user_id: DEMO_USER_ID,
        vehicle_id: DEMO_VEHICLE_ID,
        message: text,
      });
      setMessages((current) => [
        ...current,
        { role: "agent", text: response.message },
      ]);
      setRecommendedSlotIds(response.recommended_slot_ids);
      if (response.selected_slot) setSelectedSlotId(response.selected_slot);
      if (response.current_location) setConfirmedLocationId(response.current_location);
      setActiveRoute(response.route);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">P</span><span>ParkSmart<span className="brand-ai">AI</span></span></div>
        <nav aria-label="Điều hướng chính">
          <button className="nav-item active"><span>⌂</span><b>Tổng quan</b></button>
          <button className="nav-item" onClick={() => setSelectedSlotId(data.activeSession?.slot_id ?? null)}><span>⌖</span><b>Tìm xe</b></button>
          <button className="nav-item" onClick={resetDemo} disabled={pending === "reset"}><span>↻</span><b>Đặt lại demo</b></button>
        </nav>
        <div className="system-card">
          <div className="system-title"><span className="pulse" /> Dữ liệu trực tiếp</div>
          <p>Parking State Service</p>
          <div className="service-row"><span>Polling</span><strong>2 giây</strong></div>
          <div className="service-row"><span>Slots</span><strong>{data.slots.length || "—"}</strong></div>
        </div>
        <button className="profile"><span className="avatar" aria-hidden="true">MN</span><span className="profile-copy"><b>Minh Nguyễn</b><small>USER-001 · VEHICLE-001</small></span></button>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">BÃI XE PARKSMART · TẦNG F1</p><h1>Bản đồ đỗ xe trực tiếp</h1></div>
          <div className="top-actions">
            <button className="location-button" onClick={() => setShowLocationConfirm(true)}>
              <span className="location-icon">⌖</span>
              <span><small>Vị trí của bạn</small><b>{currentLocationId ?? "Chưa xác nhận"}</b></span>
              <span>⌄</span>
            </button>
          </div>
        </header>

        {actionError && <div className="page-alert" role="alert">{actionError}</div>}
        {data.error && !data.loading && <div className="page-alert" role="alert">{data.error.message}</div>}

        <div className="content-grid">
          <section className="main-column">
            {data.activeSession && (
              <div className="session-banner">
                <span className="session-icon">P</span>
                <div><small>PHIÊN ĐỖ XE ĐANG HOẠT ĐỘNG</small><b>Xe của bạn ở {data.activeSession.slot_id}</b></div>
                <button onClick={() => setSelectedSlotId(data.activeSession?.slot_id ?? null)}>Chọn ô xe</button>
              </div>
            )}

            {data.loading && <section className="card loading-card" aria-live="polite">Đang tải bản đồ canonical F1…</section>}
            {!data.loading && data.map && data.status && (
              <ParkingMap
                map={data.map}
                slots={data.slots}
                status={data.status}
                recommendedSlotIds={recommendedSlotIds}
                selectedSlotId={selectedSlotId}
                activeReservationSlotId={data.activeReservation?.slot_id}
                parkedVehicleSlotId={data.activeSession?.slot_id}
                currentLocationNodeId={currentLocationId}
                route={activeRoute}
                onSelectSlot={(slotId) => {
                  setSelectedSlotId(slotId);
                  setActiveRoute(null);
                }}
              />
            )}

            <div className="lower-grid">
              <section className="card recommend-card">
                <div className="card-header compact"><div><p className="eyebrow green">BACKEND RECOMMENDATION</p><h2>Tìm ô phù hợp</h2></div><span className="deterministic">Deterministic</span></div>
                <div className="preference-row">
                  <button className={needEv ? "selected" : ""} aria-pressed={needEv} onClick={() => setNeedEv((value) => !value)}><span>⚡</span><b>Cần sạc EV</b><small>Hard filter</small></button>
                  <button className={nearElevator ? "selected" : ""} aria-pressed={nearElevator} onClick={() => setNearElevator((value) => !value)}><span>↕</span><b>Gần thang máy</b><small>Scoring preference</small></button>
                </div>
                <button className="primary-button" onClick={recommendParking} disabled={pending === "recommend"}>Yêu cầu đề xuất <span>→</span></button>
                <div className="structured-result">
                  <b>{recommendedSlotIds.length ? `${recommendedSlotIds.length} ô được đề xuất` : "Chưa có đề xuất"}</b>
                  <p>{recommendedSlotIds.join(" · ") || "Kết quả từ POST /recommendations hoặc Agent sẽ được đánh dấu trên bản đồ."}</p>
                </div>
              </section>

              <section className="card route-card">
                <div className="card-header compact"><div><p className="eyebrow blue">SERVER ROUTING</p><h2>{selectedSlot ? `Đường tới ${selectedSlot.id}` : "Chọn một ô đích"}</h2></div><b className="distance">{activeRoute ? `${activeRoute.distance_m} m` : "—"}</b></div>
                <div className="route-contract-copy">
                  <p>{activeRoute ? activeRoute.path.join(" → ") : "Frontend chỉ hiển thị polyline do POST /routes hoặc Agent trả về."}</p>
                </div>
                <div className="action-row"><button className="secondary-button" onClick={() => setActiveRoute(null)} disabled={!activeRoute}>Ẩn đường</button><button className="primary-button" onClick={requestRoute} disabled={!selectedSlotId || pending === "route"}>Yêu cầu chỉ đường</button></div>
              </section>
            </div>
          </section>

          <aside className="assistant-card card">
            <div className="assistant-header"><div className="agent-avatar">AI<span className="online" /></div><div><h2>Trợ lý ParkSmart</h2><p><span /> Structured Agent response</p></div></div>
            <div className="conversation" aria-live="polite">
              <div className="date-separator"><span />HÔM NAY<span /></div>
              {messages.map((message, index) => <div key={`${message.role}-${index}`} className={`message ${message.role}`}><p>{message.text}</p><small>{message.role === "agent" ? "ParkSmart AI" : "Bạn"} · vừa xong</small></div>)}
            </div>
            <div className="quick-actions"><button onClick={recommendParking}>⚡ Tìm ô có sạc</button><button onClick={() => setSelectedSlotId(data.activeSession?.slot_id ?? null)}>⌖ Xe của tôi</button><button onClick={() => setShowLocationConfirm(true)}>⌖ Xác nhận vị trí</button></div>
            <form className="chat-input" onSubmit={sendMessage}>
              <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Hỏi ParkSmart AI..." aria-label="Tin nhắn cho ParkSmart AI" />
              <button type="submit" disabled={pending === "chat"} aria-label="Gửi tin nhắn">↑</button>
            </form>
            <p className="agent-note"><span>✓</span> UI chỉ hiển thị structured route và recommendation từ backend.</p>
          </aside>
        </div>
      </section>

      {showLocationConfirm && (
        <div className="modal-backdrop" onClick={() => setShowLocationConfirm(false)}>
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="location-title" onClick={(event) => event.stopPropagation()}>
            <button className="modal-close" onClick={() => setShowLocationConfirm(false)} aria-label="Đóng">×</button>
            <p className="eyebrow green">XÁC NHẬN VỊ TRÍ</p>
            <h2 id="location-title">Chọn node canonical</h2>
            <p>Vị trí được backend xác thực trước khi hiển thị trên bản đồ.</p>
            <div className="location-choice-grid">
              {selectableLocations.map((node) => (
                <button key={node.id} onClick={() => confirmLocation(node.id)} disabled={pending === "location"}>{node.id}</button>
              ))}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
