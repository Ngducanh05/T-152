"use client";

import { useState } from "react";

import { AgentComposer } from "@/components/assistant/AgentComposer";
import { ConversationActionList } from "@/components/assistant/ConversationActionList";
import { LocationPicker } from "@/components/location/LocationPicker";
import { AdjacentSlotObservation } from "@/components/parking/AdjacentSlotObservation";
import {
  WrongParkingReportDialog,
  type WrongParkingReportDraft,
} from "@/components/reports/WrongParkingReportDialog";
import { useParkSmartData } from "@/hooks/use-parksmart-data";
import { useParkingWorkflow } from "@/hooks/use-parking-workflow";
import { formatApiErrorForOperator, parkSmartApi } from "@/lib/api";
import { MVP_DEMO_USER_ID } from "@/lib/demo";
import { formatParkingLocation } from "@/lib/parking-display";
import { notifyWrongParkingReportCreated } from "@/lib/report-updates";
import { buildRouteInstructions } from "@/lib/route-instructions";

export default function Home() {
  const data = useParkSmartData();
  const workflow = useParkingWorkflow(data);
  const [manualLocationPicker, setManualLocationPicker] = useState(false);
  const [manualReportDialog, setManualReportDialog] = useState(false);

  const showLocationPicker =
    manualLocationPicker || workflow.requestedPanel?.kind === "location";
  const showReportDialog =
    manualReportDialog ||
    workflow.requestedPanel?.kind === "wrong-parking-report";
  const currentLocationSlot = data.slots.find(
    (slot) => slot.id === workflow.currentLocationId,
  );
  const requestedReportSlot =
    workflow.requestedPanel?.kind === "wrong-parking-report"
      ? workflow.requestedPanel.slotId
      : null;
  const initialReportSlotId =
    currentLocationSlot?.id ?? requestedReportSlot ?? workflow.selectedSlotId;
  const reservationLocationMatches = Boolean(
    data.activeReservation &&
      workflow.currentLocationId === data.activeReservation.slot_id,
  );
  const routeInstructions = workflow.activeRoute
    ? buildRouteInstructions(workflow.activeRoute, data.map)
    : [];
  const hasPriorityContent = Boolean(
    (data.error && !data.loading) ||
      workflow.notice ||
      data.activeReservation ||
      data.activeSession,
  );

  function closeLocationPicker() {
    setManualLocationPicker(false);
    workflow.clearRequestedPanel();
  }

  function closeReportDialog() {
    setManualReportDialog(false);
    workflow.clearRequestedPanel();
  }

  async function submitWrongParkingReport(draft: WrongParkingReportDraft) {
    await parkSmartApi.reportWrongParking({
      user_id: MVP_DEMO_USER_ID,
      slot_id: draft.slotId,
      reason_code: draft.reasonCode,
      observed_plate_number: draft.observedPlateNumber,
      description: draft.description,
    });
    notifyWrongParkingReportCreated();
  }

  return (
    <main className="chat-app-shell">
      <header className="chat-app-header">
        <div className="chat-brand" aria-label="ParkSmart AI">
          <span className="brand-mark" aria-hidden="true">P</span>
          <strong>ParkSmart<span>AI</span></strong>
        </div>
        <button
          type="button"
          className="chat-location-button"
          onClick={() => setManualLocationPicker(true)}
          aria-label={`Vị trí hiện tại: ${formatParkingLocation(workflow.currentLocationId)}. Thay đổi vị trí`}
        >
          <span aria-hidden="true">⌖</span>
          <span>
            <small>Vị trí hiện tại</small>
            <b>{formatParkingLocation(workflow.currentLocationId)}</b>
          </span>
        </button>
      </header>

      <section className="chat-workspace" aria-label="Trò chuyện với ParkSmart">
        <div className="chat-conversation" aria-live="polite">
          <div className="conversation-intro">
            <span className="agent-avatar" aria-hidden="true">AI</span>
            <div>
              <h1>Trợ lý ParkSmart</h1>
              <p>{workflow.threadId ? "Sẵn sàng hỗ trợ" : "Đang khởi tạo…"}</p>
            </div>
          </div>

          {data.loading && (
            <p className="conversation-system-status" role="status">
              Đang đồng bộ thông tin của bạn…
            </p>
          )}
          {hasPriorityContent && (
            <section
              className="conversation-priority-dock"
              aria-label="Thông tin và thao tác quan trọng"
            >
              {data.error && !data.loading && (
                <p className="conversation-alert" role="alert">
                  {formatApiErrorForOperator(data.error, "Không thể tải thông tin của bạn.")}
                </p>
              )}
              {workflow.notice && (
                <p className="conversation-notice" role="status" aria-live="polite">
                  {workflow.notice}
                </p>
              )}

              {data.activeReservation && (
                <article className="conversation-state-card reservation-state-card" aria-label="Chỗ đỗ đã giữ">
              <span className="state-card-icon" aria-hidden="true">R</span>
              <div>
                <small>CHỖ ĐỖ ĐÃ GIỮ</small>
                <h2>{formatParkingLocation(data.activeReservation.slot_id)}</h2>
                <p>
                  {reservationLocationMatches
                    ? "Vị trí của bạn trùng với ô đã giữ."
                    : "Khi đến cạnh đúng ô, hãy cập nhật vị trí để xác nhận đã đỗ."}
                </p>
              </div>
              {reservationLocationMatches ? (
                <button
                  type="button"
                  onClick={() => void workflow.confirmParking()}
                  disabled={workflow.pending === "confirm-parking"}
                >
                  {workflow.pending === "confirm-parking"
                    ? "Đang xác nhận…"
                    : "Xác nhận đã đỗ"}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => void workflow.confirmParking()}
                  disabled={workflow.pending === "confirm-parking"}
                >
                  {workflow.pending === "confirm-parking"
                    ? "Đang xác nhận đến nơi…"
                    : "Tôi đã đến nơi"}
                </button>
              )}
                </article>
              )}

              {data.activeSession && (
                <>
                  <article className="conversation-state-card session-state-card" aria-label="Xe đang đỗ trong bãi">
              <span className="state-card-icon" aria-hidden="true">P</span>
              <div>
                <small>XE CỦA BẠN</small>
                <h2>{formatParkingLocation(data.activeSession.slot_id)}</h2>
                <p>Phiên đỗ xe đang hoạt động.</p>
              </div>
              <div className="state-card-actions">
                <button
                  type="button"
                  onClick={() => void workflow.findVehicleAndRoute()}
                  disabled={workflow.pending === "find-car"}
                >
                  Chỉ đường tới xe
                </button>
                <button
                  type="button"
                  className="danger-text-button"
                  onClick={() => void workflow.completeSession()}
                  disabled={workflow.pending === "complete-session"}
                >
                  Kết thúc phiên
                </button>
              </div>
                  </article>
                  <AdjacentSlotObservation
                    parkedSlotId={data.activeSession.slot_id}
                    slots={data.slots}
                    pendingSlotId={workflow.pendingAdjacentSlotId}
                    onObserve={workflow.updateAdjacentSlotStatus}
                  />
                </>
              )}
            </section>
          )}

          {workflow.messages.map((message) => (
            <article key={message.id} className={`chat-message message-${message.role}`}>
              <div className="message-card">
                <p>{message.text}</p>
                <small>{message.role === "agent" ? "ParkSmart AI" : "Bạn"}</small>
              </div>
              {message.role === "agent" && (
                <ConversationActionList
                  message={message}
                  pending={workflow.pending !== null}
                  onAction={workflow.executeUiAction}
                />
              )}
            </article>
          ))}

          {workflow.activeRoute && (
            <article className="conversation-route-card" aria-label="Chỉ đường trong bãi">
              <header>
                <div>
                  <small>CHỈ ĐƯỜNG TRONG BÃI</small>
                  <h2>
                    Đến {formatParkingLocation(workflow.activeRoute.path.at(-1))}
                  </h2>
                </div>
                <strong>{workflow.activeRoute.distance_m} m</strong>
              </header>
              <ol>
                {routeInstructions.map((instruction, index) => (
                  <li key={`${instruction.nodeId}-${index}`}>
                    <span
                      className={`route-instruction-icon route-${instruction.kind.toLowerCase()}`}
                      aria-hidden="true"
                    >
                      {instruction.icon}
                    </span>
                    <div>
                      <b>{instruction.label}</b>
                      <p>{instruction.description}</p>
                    </div>
                  </li>
                ))}
              </ol>
              <p>
                Hướng rẽ được tính từ hình học tuyến đường do backend trả về,
                không lấy từ nội dung do AI tự diễn giải.
              </p>
            </article>
          )}

          {workflow.pending === "chat" && (
            <div className="chat-loading" role="status">
              <i /><i /><i /><span>ParkSmart đang xử lý…</span>
            </div>
          )}
          {workflow.retryMessage && (
            <button
              type="button"
              className="agent-retry"
              onClick={() => void workflow.retryAgentMessage()}
              disabled={workflow.pending === "chat"}
            >
              Thử gửi lại
            </button>
          )}
        </div>

        <footer className="chat-composer-dock">
          <AgentComposer
            onSend={workflow.sendAgentMessage}
            threadReady={Boolean(workflow.threadId)}
            chatPending={workflow.pending === "chat"}
          />
        </footer>
      </section>

      {showLocationPicker && (
        <LocationPicker
          map={data.map}
          currentLocationId={workflow.currentLocationId}
          pending={workflow.pending === "location"}
          errorMessage={workflow.notice}
          onClose={closeLocationPicker}
          onConfirm={workflow.confirmLocation}
        />
      )}
      {showReportDialog && (
        <WrongParkingReportDialog
          slots={data.slots}
          initialSlotId={initialReportSlotId}
          onClose={closeReportDialog}
          onSubmit={submitWrongParkingReport}
        />
      )}
    </main>
  );
}
