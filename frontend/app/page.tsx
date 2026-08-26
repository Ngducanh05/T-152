"use client";

import { useState } from "react";

import { AgentComposer } from "@/components/assistant/AgentComposer";
import { ConversationActionList } from "@/components/assistant/ConversationActionList";
import {
  parkingIdentityFromProfile,
  useAuth,
} from "@/components/auth/AuthProvider";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { LocationPicker } from "@/components/location/LocationPicker";
import { LocationQrScanner } from "@/components/location/LocationQrScanner";
import { AdjacentSlotObservation } from "@/components/parking/AdjacentSlotObservation";
import { RewardSummaryCard } from "@/components/rewards/RewardSummaryCard";
import {
  WrongParkingReportDialog,
  type WrongParkingReportDraft,
} from "@/components/reports/WrongParkingReportDialog";
import { useParkSmartData } from "@/hooks/use-parksmart-data";
import { useParkingWorkflow } from "@/hooks/use-parking-workflow";
import { formatApiErrorForOperator, parkSmartApi } from "@/lib/api";
import type { ParkingIdentity } from "@/lib/auth";
import { formatParkingLocation } from "@/lib/parking-display";
import { isAgentEnabled } from "@/lib/public-config";
import { notifyWrongParkingReportCreated } from "@/lib/report-updates";
import { buildRouteInstructions } from "@/lib/route-instructions";
import type { ChatUiAction } from "@/lib/types";

export default function Home() {
  return (
    <ProtectedRoute requiredRole="user">
      <AuthenticatedHome />
    </ProtectedRoute>
  );
}

function AuthenticatedHome() {
  const { profile } = useAuth();
  const identity = profile ? parkingIdentityFromProfile(profile) : null;
  if (!identity) return null;
  return <ParkSmartUserApp identity={identity} />;
}

function ParkSmartUserApp({ identity }: { identity: ParkingIdentity }) {
  const agentEnabled = isAgentEnabled();
  const { refreshProfile } = useAuth();
  const data = useParkSmartData(parkSmartApi, identity.userId);
  const workflow = useParkingWorkflow(data, parkSmartApi, identity);
  const [manualLocationPicker, setManualLocationPicker] = useState(false);
  const [manualReportDialog, setManualReportDialog] = useState(false);
  const [firstVehicleDialogOpen, setFirstVehicleDialogOpen] = useState(false);

  const showLocationPicker =
    manualLocationPicker || workflow.requestedPanel?.kind === "location";
  const showQrScanner = workflow.requestedPanel?.kind === "qr-location";
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

  function closeQrScanner() {
    workflow.clearRequestedPanel();
  }

  function openManualLocationFromQr() {
    workflow.clearRequestedPanel();
    setManualLocationPicker(true);
  }

  function closeReportDialog() {
    setManualReportDialog(false);
    workflow.clearRequestedPanel();
  }

  async function submitWrongParkingReport(draft: WrongParkingReportDraft) {
    const report = await parkSmartApi.reportWrongParking({
      user_id: identity.userId,
      slot_id: draft.slotId,
      reason_code: draft.reasonCode,
      observed_plate_number: draft.observedPlateNumber,
      description: draft.description,
      evidence: draft.evidence ?? undefined,
    });
    await data.refresh();
    notifyWrongParkingReportCreated();
    return report;
  }

  function requireVehicle(action: () => void) {
    if (!identity.vehicleId) {
      setFirstVehicleDialogOpen(true);
      return;
    }
    action();
  }

  async function handleUiAction(messageId: string, action: ChatUiAction) {
    const requiresVehicle = [
      "FIND_VEHICLE",
      "RESERVE_AND_ROUTE",
      "CONFIRM_PARKING",
      "COMPLETE_SESSION",
    ].includes(action.type);
    if (requiresVehicle) {
      requireVehicle(() => void workflow.executeUiAction(messageId, action));
      return;
    }
    await workflow.executeUiAction(messageId, action);
  }

  return (
    <main className="chat-app-shell">
      <header className="chat-app-header">
        <div className="chat-brand" aria-label="ParkSmart AI">
          <span className="brand-mark" aria-hidden="true">P</span>
          <strong>ParkSmart<span>AI</span></strong>
        </div>
        <LogoutButton />
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
          {!identity.vehicleId && (
            <section className="conversation-priority-dock" aria-label="Thiết lập xe">
              <article className="conversation-state-card reservation-state-card">
                <span className="state-card-icon" aria-hidden="true">+</span>
                <div>
                  <small>THIẾT LẬP TÀI KHOẢN</small>
                  <h2>Thêm xe đầu tiên</h2>
                  <p>Thêm biển số để giữ chỗ, xác nhận đỗ và tìm đường về xe.</p>
                </div>
                <button type="button" onClick={() => setFirstVehicleDialogOpen(true)}>
                  Thêm xe
                </button>
              </article>
            </section>
          )}
          {data.rewardSummary && (
            <RewardSummaryCard
              summary={data.rewardSummary}
              contributions={data.contributions}
            />
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
                  onClick={() => requireVehicle(() => void workflow.confirmParking())}
                  disabled={workflow.pending === "confirm-parking"}
                >
                  {workflow.pending === "confirm-parking"
                    ? "Đang xác nhận…"
                    : "Xác nhận đã đỗ"}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => requireVehicle(() => void workflow.confirmParking())}
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
                  onClick={() => requireVehicle(() => void workflow.findVehicleAndRoute())}
                  disabled={workflow.pending === "find-car"}
                >
                  Chỉ đường tới xe
                </button>
                <button
                  type="button"
                  className="danger-text-button"
                  onClick={() => requireVehicle(() => void workflow.completeSession())}
                  disabled={workflow.pending === "complete-session"}
                >
                  Kết thúc phiên
                </button>
              </div>
                  </article>
                  <AdjacentSlotObservation
                    key={data.activeSession.session_id}
                    parkingSessionId={data.activeSession.session_id}
                    parkedSlotId={data.activeSession.slot_id}
                    slots={data.slots}
                    observedSlotIds={(data.contributions ?? [])
                      .filter(
                        (contribution) =>
                          contribution.source_type ===
                            "ADJACENT_SLOT_OBSERVATION" &&
                          contribution.observer_session_id ===
                            data.activeSession?.session_id,
                      )
                      .map((contribution) => contribution.slot_id)}
                    rewardPoints={
                      data.rewardConfiguration?.adjacent_observation_reward_points ?? 0
                    }
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
                  onAction={handleUiAction}
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
            </article>
          )}

          {agentEnabled && workflow.pending === "chat" && (
            <div className="chat-loading" role="status">
              <i /><i /><i /><span>ParkSmart đang xử lý…</span>
            </div>
          )}
          {agentEnabled && workflow.retryMessage && (
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
          {agentEnabled ? (
            <AgentComposer
              onSend={workflow.sendAgentMessage}
              threadReady={Boolean(workflow.threadId)}
              chatPending={workflow.pending === "chat"}
            />
          ) : (
            <p className="agent-note" role="status">
              Trợ lý AI hiện đang tạm tắt. Bạn vẫn có thể sử dụng các thao tác
              tìm chỗ, giữ chỗ và báo sự cố.
            </p>
          )}
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
      {showQrScanner && (
        <LocationQrScanner
          pending={workflow.pending === "qr-location"}
          errorMessage={workflow.notice}
          onClose={closeQrScanner}
          onScan={workflow.scanLocationQr}
          onManualFallback={openManualLocationFromQr}
        />
      )}
      {showReportDialog && (
        <WrongParkingReportDialog
          slots={data.slots}
          initialSlotId={initialReportSlotId}
          rewardPoints={
            data.rewardConfiguration?.wrong_parking_report_reward_points ?? 0
          }
          onClose={closeReportDialog}
          onSubmit={submitWrongParkingReport}
        />
      )}
      {firstVehicleDialogOpen && (
        <FirstVehicleDialog
          onClose={() => setFirstVehicleDialogOpen(false)}
          onCreated={async () => {
            setFirstVehicleDialogOpen(false);
            await refreshProfile();
          }}
        />
      )}
    </main>
  );
}

function FirstVehicleDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const [plateNumber, setPlateNumber] = useState("");
  const [requiresCharging, setRequiresCharging] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (pending || plateNumber.trim().length < 2) return;
    setPending(true);
    setError(null);
    try {
      await parkSmartApi.addVehicle({
        plate_number: plateNumber.trim().toUpperCase(),
        requires_charging: requiresCharging,
      });
      await onCreated();
    } catch (submitError) {
      setError(formatApiErrorForOperator(submitError, "Không thể thêm xe."));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => !pending && onClose()}>
      <section
        className="modal first-vehicle-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="first-vehicle-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          className="modal-close"
          onClick={onClose}
          disabled={pending}
          aria-label="Đóng"
        >
          ×
        </button>
        <h2 id="first-vehicle-title">Thêm xe đầu tiên</h2>
        <label className="vehicle-plate-field">
          Biển số xe
          <input
            type="text"
            name="plate-number"
            className="vehicle-plate-input"
            value={plateNumber}
            onChange={(event) => setPlateNumber(event.target.value.toUpperCase())}
            placeholder="Ví dụ: 59A1-123.45"
            maxLength={32}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            disabled={pending}
          />
        </label>
        <label className="vehicle-charge-option">
          <input
            type="checkbox"
            checked={requiresCharging}
            onChange={(event) => setRequiresCharging(event.target.checked)}
            disabled={pending}
          />
          Xe cần sạc điện
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button
          type="button"
          className="primary-button"
          onClick={() => void submit()}
          disabled={pending || plateNumber.trim().length < 2}
        >
          {pending ? "Đang thêm…" : "Lưu xe"}
        </button>
      </section>
    </div>
  );
}
