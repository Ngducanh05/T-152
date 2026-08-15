"use client";

import { useState } from "react";

import { AgentComposer } from "@/components/assistant/AgentComposer";
import { LocationConfirmationOutcome } from "@/components/location/LocationConfirmationOutcome";
import { LocationPicker } from "@/components/location/LocationPicker";
import { ParkingMap } from "@/components/parking/ParkingMap";
import { useParkingWorkflow } from "@/hooks/use-parking-workflow";
import { formatApiErrorForOperator } from "@/lib/api";
import { useParkSmartData } from "@/hooks/use-parksmart-data";
import { MVP_DEMO_USER_ID, MVP_DEMO_VEHICLE_ID } from "@/lib/demo";

export default function Home() {
  const data = useParkSmartData();
  const workflow = useParkingWorkflow(data);
  const [needEv, setNeedEv] = useState(true);
  const [needAccessible, setNeedAccessible] = useState(false);
  const [nearElevator, setNearElevator] = useState(true);
  const [showLocationConfirm, setShowLocationConfirm] = useState(false);

  const selectedSlot =
    data.slots.find((slot) => slot.id === workflow.selectedSlotId) ?? null;
  const currentLocationNode =
    data.map?.nodes.find((node) => node.id === workflow.currentLocationId) ?? null;
  const currentLocationIsSlot = currentLocationNode?.type === "SLOT";

  function requestRecommendations() {
    void workflow.requestRecommendations({
      chargingRequired: needEv,
      accessibleRequired: needAccessible,
      nearElevator,
    });
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">P</span><span>ParkSmart<span className="brand-ai">AI</span></span></div>
        <nav aria-label="Điều hướng chính">
          <button className="nav-item active"><span>⌂</span><b>Tổng quan</b></button>
          <button className="nav-item" onClick={() => void workflow.findVehicleAndRoute()} disabled={workflow.pending === "find-car"}><span>⌖</span><b>Tìm xe</b></button>
          <button className="nav-item" onClick={() => void workflow.resetDemo()} disabled={workflow.pending === "reset"}><span>↻</span><b>Đặt lại demo</b></button>
        </nav>
        <div className="system-card">
          <div className="system-title"><span className="pulse" /> Dữ liệu trực tiếp</div>
          <p>Parking State Service</p>
          <div className="service-row"><span>Polling</span><strong>2 giây</strong></div>
          <div className="service-row"><span>Slots</span><strong>{data.slots.length || "—"}</strong></div>
        </div>
        <div className="profile"><span className="avatar" aria-hidden="true">MN</span><span className="profile-copy"><b>MVP Demo</b><small>{MVP_DEMO_USER_ID} · {MVP_DEMO_VEHICLE_ID}</small></span></div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">BÃI XE PARKSMART · TẦNG F1</p><h1>Bản đồ đỗ xe trực tiếp</h1></div>
          <div className="top-actions">
            <button className="location-button" onClick={() => setShowLocationConfirm(true)}>
              <span className="location-icon">⌖</span>
              <span><small>Vị trí đã xác nhận</small><b>{workflow.currentLocationId ?? "Chưa xác nhận"}</b></span>
              <span>⌄</span>
            </button>
          </div>
        </header>

        {workflow.notice && !showLocationConfirm && <div className="page-alert" role="alert">{workflow.notice}</div>}
        {data.error && !data.loading && <div className="page-alert" role="alert">{formatApiErrorForOperator(data.error, "Không thể tải dữ liệu bãi xe.")}</div>}

        <div className="content-grid">
          <section className="main-column">
            {data.activeReservation && (
              <div className="reservation-banner" role="status" aria-label="Active reservation">
                <span className="session-icon">R</span>
                <div><small>RESERVATION ĐANG HOẠT ĐỘNG</small><b>{data.activeReservation.slot_id}</b></div>
                {!currentLocationIsSlot && <button onClick={() => void workflow.confirmParking()} disabled={workflow.pending === "confirm-parking"}>Xác nhận đã đỗ</button>}
              </div>
            )}
            {currentLocationIsSlot && currentLocationNode && (
              <LocationConfirmationOutcome
                locationId={currentLocationNode.id}
                activeReservation={data.activeReservation}
                pending={workflow.pending === "confirm-parking"}
                onConfirmParking={workflow.confirmParking}
              />
            )}
            {data.activeSession && (
              <div className="session-banner" role="status" aria-label="Active parking session">
                <span className="session-icon">P</span>
                <div><small>PHIÊN ĐỖ XE ĐANG HOẠT ĐỘNG</small><b>Xe của bạn ở {data.activeSession.slot_id}</b></div>
                <button onClick={() => void workflow.findVehicleAndRoute()} disabled={workflow.pending === "find-car"}>Chỉ đường tới xe</button>
                <button className="text-button" onClick={() => void workflow.completeSession()} disabled={workflow.pending === "complete-session"}>Kết thúc</button>
              </div>
            )}

            {data.loading && <section className="card loading-card" aria-live="polite">Đang tải trạng thái authoritative…</section>}
            {!data.loading && data.map && data.status && (
              <ParkingMap
                map={data.map}
                slots={data.slots}
                status={data.status}
                recommendedSlotIds={workflow.recommendedSlotIds}
                selectedSlotId={workflow.selectedSlotId}
                activeReservationSlotId={data.activeReservation?.slot_id}
                parkedVehicleSlotId={data.activeSession?.slot_id}
                currentLocationNodeId={workflow.currentLocationId}
                route={workflow.activeRoute}
                onSelectSlot={workflow.selectCandidate}
              />
            )}

            <div className="lower-grid">
              <section className="card recommend-card">
                <div className="card-header compact"><div><p className="eyebrow green">POST /RECOMMENDATIONS</p><h2>Tìm và chọn ô</h2></div><span className="deterministic">Không tự giữ chỗ</span></div>
                <div className="preference-row three-options">
                  <button className={needEv ? "selected" : ""} aria-pressed={needEv} onClick={() => setNeedEv((value) => !value)}><span>⚡</span><b>Cần sạc EV</b><small>Hard filter</small></button>
                  <button className={needAccessible ? "selected" : ""} aria-pressed={needAccessible} onClick={() => setNeedAccessible((value) => !value)}><span>♿</span><b>Tiếp cận</b><small>Hard filter</small></button>
                  <button className={nearElevator ? "selected" : ""} aria-pressed={nearElevator} onClick={() => setNearElevator((value) => !value)}><span>↕</span><b>Gần thang máy</b><small>Soft preference</small></button>
                </div>
                <button className="primary-button" onClick={requestRecommendations} disabled={workflow.pending === "recommend"}>Yêu cầu đề xuất <span>→</span></button>
                <div className="candidate-list" aria-label="Các ô được đề xuất">
                  {workflow.candidates.length === 0 && <p>Recommendation chỉ highlight candidate; chưa có slot nào được giữ.</p>}
                  {workflow.candidates.map((candidate) => (
                    <button
                      key={candidate.slot_id}
                      className={workflow.selectedSlotId === candidate.slot_id ? "selected" : ""}
                      onClick={() => workflow.selectCandidate(candidate.slot_id)}
                      aria-pressed={workflow.selectedSlotId === candidate.slot_id}
                    >
                      <b>{candidate.slot_id}</b>
                      <span>{candidate.distance_m} m · {candidate.score} điểm</span>
                    </button>
                  ))}
                </div>
                {selectedSlot && (
                  <div className={`selected-slot-detail status-${selectedSlot.status.toLowerCase()}`} aria-live="polite">
                    <div>
                      <small>Ô đang chọn</small>
                      <b>{selectedSlot.id}</b>
                    </div>
                    <div>
                      <small>Trạng thái hiện tại</small>
                      <strong>{selectedSlot.status === "AVAILABLE" ? "Đang trống" : selectedSlot.status === "RESERVED" ? "Đã được giữ" : "Đã có xe"}</strong>
                    </div>
                    <span>Khu {selectedSlot.zone_id}{selectedSlot.has_charger ? " · Có sạc EV" : ""}{selectedSlot.is_accessible ? " · Tiếp cận" : ""}</span>
                  </div>
                )}
                <div className="workflow-actions">
                  <button className="secondary-button" onClick={() => void workflow.reserveSelected()} disabled={!selectedSlot || selectedSlot.status !== "AVAILABLE" || workflow.pending === "reserve" || Boolean(data.activeReservation)}>Chọn làm điểm đỗ</button>
                  <button className="primary-button" onClick={() => void workflow.requestRouteToSelected()} disabled={!workflow.selectedSlotId || workflow.pending === "route"}>Chỉ đường</button>
                </div>
              </section>

              <section className="card route-card">
                <div className="card-header compact"><div><p className="eyebrow blue">SERVER ROUTING</p><h2>{selectedSlot ? `Đường tới ${selectedSlot.id}` : "Chưa chọn đích"}</h2></div><b className="distance">{workflow.activeRoute ? `${workflow.activeRoute.distance_m} m` : "—"}</b></div>
                <div className="route-contract-copy"><p>{workflow.activeRoute ? workflow.activeRoute.path.join(" → ") : "UI chỉ vẽ polyline do backend trả về."}</p></div>
                <div className="workflow-stack">
                  <button className="secondary-button" onClick={workflow.clearRoute} disabled={!workflow.activeRoute}>Ẩn đường</button>
                  <button className="secondary-button" onClick={() => void workflow.findVehicleAndRoute()} disabled={workflow.pending === "find-car"}>Tìm xe và chỉ đường</button>
                  <button className="primary-button" onClick={() => void workflow.completeSession()} disabled={!data.activeSession || workflow.pending === "complete-session"}>Kết thúc phiên đỗ</button>
                </div>
              </section>
            </div>
          </section>

          <aside className="assistant-card card">
            <div className="assistant-header"><div className="agent-avatar">AI<span className="online" /></div><div><h2>Trợ lý ParkSmart</h2><p><span /> Thread {workflow.threadId?.slice(-8) ?? "đang tạo"}</p></div></div>
            <div className="conversation" aria-live="polite">
              <div className="date-separator"><span />HÔM NAY<span /></div>
              {workflow.messages.length === 0 && <div className="message agent"><p>Hãy dùng các nút trực tiếp cho luồng đỗ xe hoặc gửi yêu cầu cho Agent.</p></div>}
              {workflow.messages.map((message, index) => <div key={`${message.role}-${index}`} className={`message ${message.role}`}><p>{message.text}</p><small>{message.role === "agent" ? "ParkSmart AI" : "Bạn"} · vừa xong</small></div>)}
              {workflow.pending === "chat" && <div className="chat-loading" role="status"><i /><i /><i /><span>ParkSmart đang xử lý…</span></div>}
            </div>
            {workflow.lastToolNames.length > 0 && <div className="tool-summary" aria-label="Công cụ Agent đã dùng">Tools: {workflow.lastToolNames.join(" · ")}</div>}
            {workflow.retryMessage && <button className="agent-retry" onClick={() => void workflow.retryAgentMessage()} disabled={workflow.pending === "chat"}>Thử gửi lại</button>}
            <div className="quick-actions"><button onClick={requestRecommendations}>⚡ Tìm ô có sạc</button><button onClick={() => void workflow.findVehicleAndRoute()}>⌖ Xe của tôi</button><button onClick={() => setShowLocationConfirm(true)}>⌖ Xác nhận vị trí</button></div>
            <AgentComposer
              onSend={workflow.sendAgentMessage}
              threadReady={Boolean(workflow.threadId)}
              chatPending={workflow.pending === "chat"}
            />
            <p className="agent-note"><span>✓</span> Mọi mutation chờ backend thành công rồi tải lại trạng thái authoritative.</p>
          </aside>
        </div>
      </section>

      {showLocationConfirm && (
        <LocationPicker
          map={data.map}
          currentLocationId={workflow.currentLocationId}
          pending={workflow.pending === "location"}
          errorMessage={workflow.notice}
          onClose={() => setShowLocationConfirm(false)}
          onConfirm={workflow.confirmLocation}
        />
      )}
    </main>
  );
}
