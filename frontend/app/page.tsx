"use client";

import { useState } from "react";

import { AgentComposer } from "@/components/assistant/AgentComposer";
import { LocationConfirmationOutcome } from "@/components/location/LocationConfirmationOutcome";
import { LocationPicker } from "@/components/location/LocationPicker";
import { ParkingMap } from "@/components/parking/ParkingMap";
import {
  WrongParkingReportDialog,
  type WrongParkingReportDraft,
} from "@/components/reports/WrongParkingReportDialog";
import { useParkSmartData } from "@/hooks/use-parksmart-data";
import { useParkingWorkflow } from "@/hooks/use-parking-workflow";
import { formatApiErrorForOperator, parkSmartApi } from "@/lib/api";
import { MVP_DEMO_USER_ID } from "@/lib/demo";
import { formatParkingLocation, formatSlotStatus } from "@/lib/parking-display";
import { notifyWrongParkingReportCreated } from "@/lib/report-updates";

export default function Home() {
  const data = useParkSmartData();
  const workflow = useParkingWorkflow(data);
  const [needEv, setNeedEv] = useState(true);
  const [needAccessible, setNeedAccessible] = useState(false);
  const [nearElevator, setNearElevator] = useState(true);
  const [showLocationConfirm, setShowLocationConfirm] = useState(false);
  const [showWrongParkingReport, setShowWrongParkingReport] = useState(false);

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

  async function submitWrongParkingReport(draft: WrongParkingReportDraft) {
    await parkSmartApi.reportWrongParking({
      user_id: MVP_DEMO_USER_ID,
      slot_id: draft.slotId,
      observed_plate_number: draft.observedPlateNumber,
      description: draft.description,
    });
    notifyWrongParkingReportCreated();
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">P</span><span>ParkSmart<span className="brand-ai">AI</span></span></div>
        <nav aria-label="Điều hướng chính">
          <button className="nav-item active"><span>⌂</span><b>Tổng quan</b></button>
          <button className="nav-item" onClick={() => void workflow.findVehicleAndRoute()} disabled={workflow.pending === "find-car"}><span>⌖</span><b>Tìm xe</b></button>
          <button className="nav-item" onClick={() => setShowWrongParkingReport(true)} disabled={data.slots.length === 0}><span>!</span><b>Báo xe đỗ sai</b></button>
        </nav>
        <div className="profile"><span className="avatar" aria-hidden="true">PS</span><span className="profile-copy"><b>Người dùng thử nghiệm</b><small>Trải nghiệm đỗ xe thông minh</small></span></div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">BÃI XE PARKSMART · TẦNG F1</p><h1>Tìm chỗ đỗ phù hợp</h1></div>
          <div className="top-actions">
            <button className="location-button" onClick={() => setShowLocationConfirm(true)}>
              <span className="location-icon">⌖</span>
              <span><small>Vị trí của bạn</small><b>{formatParkingLocation(workflow.currentLocationId)}</b></span>
              <span>⌄</span>
            </button>
          </div>
        </header>

        {workflow.notice && !showLocationConfirm && <div className="page-alert" role="alert">{workflow.notice}</div>}
        {data.error && !data.loading && <div className="page-alert" role="alert">{formatApiErrorForOperator(data.error, "Không thể tải dữ liệu bãi xe.")}</div>}

        <div className="content-grid">
          <section className="main-column">
            {data.activeReservation && (
              <div className="reservation-banner" role="status" aria-label="Chỗ đỗ đã giữ">
                <span className="session-icon">R</span>
                <div><small>CHỖ ĐỖ ĐÃ GIỮ</small><b>{formatParkingLocation(data.activeReservation.slot_id)}</b></div>
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
              <div className="session-banner" role="status" aria-label="Xe đang đỗ trong bãi">
                <span className="session-icon">P</span>
                <div><small>XE CỦA BẠN ĐANG Ở TRONG BÃI</small><b>{formatParkingLocation(data.activeSession.slot_id)}</b></div>
                <button onClick={() => void workflow.findVehicleAndRoute()} disabled={workflow.pending === "find-car"}>Chỉ đường tới xe</button>
                <button className="text-button" onClick={() => void workflow.completeSession()} disabled={workflow.pending === "complete-session"}>Kết thúc</button>
              </div>
            )}

            {data.loading && <section className="card loading-card" aria-live="polite">Đang tải thông tin bãi xe…</section>}
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
                <div className="card-header compact"><div><p className="eyebrow green">GỢI Ý CHỖ ĐỖ</p><h2>Tìm và chọn ô</h2></div><span className="deterministic">Bạn luôn là người xác nhận</span></div>
                <div className="preference-row three-options">
                  <button className={needEv ? "selected" : ""} aria-pressed={needEv} onClick={() => setNeedEv((value) => !value)}><span>⚡</span><b>Cần sạc EV</b><small>Chỉ tìm ô có sạc</small></button>
                  <button className={needAccessible ? "selected" : ""} aria-pressed={needAccessible} onClick={() => setNeedAccessible((value) => !value)}><span>♿</span><b>Dễ tiếp cận</b><small>Phù hợp nhu cầu hỗ trợ</small></button>
                  <button className={nearElevator ? "selected" : ""} aria-pressed={nearElevator} onClick={() => setNearElevator((value) => !value)}><span>↕</span><b>Gần thang máy</b><small>Ưu tiên quãng đường thuận tiện</small></button>
                </div>
                <button className="primary-button" onClick={requestRecommendations} disabled={workflow.pending === "recommend"}>Tìm chỗ phù hợp <span>→</span></button>
                <div className="candidate-list" aria-label="Các ô được đề xuất">
                  {workflow.candidates.length === 0 && <p>Chọn nhu cầu của bạn rồi nhấn “Tìm chỗ phù hợp”. Chỉ khi bạn xác nhận thì ô mới được giữ.</p>}
                  {workflow.candidates.map((candidate) => (
                    <button
                      key={candidate.slot_id}
                      data-slot-id={candidate.slot_id}
                      className={workflow.selectedSlotId === candidate.slot_id ? "selected" : ""}
                      onClick={() => workflow.selectCandidate(candidate.slot_id)}
                      aria-pressed={workflow.selectedSlotId === candidate.slot_id}
                    >
                      <b>{formatParkingLocation(candidate.slot_id)}</b>
                      <span>{candidate.distance_m} m · {candidate.score} điểm</span>
                    </button>
                  ))}
                </div>
                {selectedSlot && (
                  <div className={`selected-slot-detail status-${selectedSlot.status.toLowerCase()}`} aria-live="polite">
                    <div>
                      <small>Ô đang chọn</small>
                      <b>{formatParkingLocation(selectedSlot.id)}</b>
                    </div>
                    <div>
                      <small>Trạng thái hiện tại</small>
                      <strong>{formatSlotStatus(selectedSlot.status)}</strong>
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
                <div className="card-header compact"><div><p className="eyebrow blue">CHỈ ĐƯỜNG TRONG BÃI</p><h2>{selectedSlot ? `Đường tới ${formatParkingLocation(selectedSlot.id)}` : "Chưa chọn điểm đến"}</h2></div><b className="distance">{workflow.activeRoute ? `${workflow.activeRoute.distance_m} m` : "—"}</b></div>
                <div className="route-contract-copy"><p>{workflow.activeRoute ? `Đường đi đã hiển thị trên bản đồ. Quãng đường dự kiến ${workflow.activeRoute.distance_m} m.` : "Chọn một ô đỗ hoặc tìm xe để xem đường đi trên bản đồ."}</p></div>
                <div className="workflow-stack">
                  <button className="secondary-button" onClick={workflow.clearRoute} disabled={!workflow.activeRoute}>Ẩn đường</button>
                  <button className="secondary-button" onClick={() => void workflow.findVehicleAndRoute()} disabled={workflow.pending === "find-car"}>Tìm xe và chỉ đường</button>
                  <button className="primary-button" onClick={() => void workflow.completeSession()} disabled={!data.activeSession || workflow.pending === "complete-session"}>Kết thúc phiên đỗ</button>
                </div>
              </section>
            </div>
          </section>

          <aside className="assistant-card card">
            <div className="assistant-header"><div className="agent-avatar">AI<span className="online" /></div><div><h2>Trợ lý ParkSmart</h2><p><span /> {workflow.threadId ? "Sẵn sàng hỗ trợ" : "Đang khởi tạo"}</p></div></div>
            <div className="conversation" aria-live="polite">
              <div className="date-separator"><span />HÔM NAY<span /></div>
              {workflow.messages.length === 0 && <div className="message agent"><p>Bạn muốn tìm chỗ đỗ, chỉ đường hay tìm lại xe? Tôi luôn chờ bạn xác nhận trước khi thực hiện.</p></div>}
              {workflow.messages.map((message, index) => <div key={`${message.role}-${index}`} className={`message ${message.role}`}><p>{message.text}</p><small>{message.role === "agent" ? "ParkSmart AI" : "Bạn"} · vừa xong</small></div>)}
              {workflow.pending === "chat" && <div className="chat-loading" role="status"><i /><i /><i /><span>ParkSmart đang xử lý…</span></div>}
            </div>
            {workflow.retryMessage && <button className="agent-retry" onClick={() => void workflow.retryAgentMessage()} disabled={workflow.pending === "chat"}>Thử gửi lại</button>}
            <div className="quick-actions"><button onClick={requestRecommendations}>⚡ Tìm ô có sạc</button><button onClick={() => void workflow.findVehicleAndRoute()}>⌖ Xe của tôi</button><button onClick={() => setShowLocationConfirm(true)}>⌖ Xác nhận vị trí</button></div>
            <AgentComposer
              onSend={workflow.sendAgentMessage}
              threadReady={Boolean(workflow.threadId)}
              chatPending={workflow.pending === "chat"}
            />
            <p className="agent-note"><span>✓</span> Thông tin bãi xe được làm mới sau mỗi thao tác thành công.</p>
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
      {showWrongParkingReport && (
        <WrongParkingReportDialog
          slots={data.slots}
          initialSlotId={workflow.selectedSlotId}
          onClose={() => setShowWrongParkingReport(false)}
          onSubmit={submitWrongParkingReport}
        />
      )}
    </main>
  );
}
