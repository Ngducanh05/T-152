"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AgentComposer } from "@/components/assistant/AgentComposer";
import { ConversationActionList } from "@/components/assistant/ConversationActionList";
import {
  parkingIdentityFromProfile,
  useAuth,
} from "@/components/auth/AuthProvider";
import { LogoutButton } from "@/components/auth/LogoutButton";
import authStyles from "@/components/auth/auth.module.css";
import { LocationPicker } from "@/components/location/LocationPicker";
import { AdjacentSlotObservation } from "@/components/parking/AdjacentSlotObservation";
import {
  WrongParkingReportDialog,
  type WrongParkingReportDraft,
} from "@/components/reports/WrongParkingReportDialog";
import { useParkSmartData } from "@/hooks/use-parksmart-data";
import { useParkingWorkflow } from "@/hooks/use-parking-workflow";
import { formatApiErrorForOperator, parkSmartApi } from "@/lib/api";
import { formatParkingLocation } from "@/lib/parking-display";
import { notifyWrongParkingReportCreated } from "@/lib/report-updates";
import { buildRouteInstructions } from "@/lib/route-instructions";
import type { ChatUiAction } from "@/lib/types";

type PendingIntent =
  | { type: "find-parking" }
  | { type: "find-vehicle" }
  | { type: "location" }
  | { type: "report" }
  | { type: "chat"; message: string };

type VehiclePendingIntent =
  | { type: "find-vehicle" }
  | { type: "reserve-and-route"; slotId?: string }
  | { type: "confirm-parking" }
  | { type: "complete-session" }
  | { type: "ui-action"; messageId: string; action: ChatUiAction };

const PENDING_INTENT_KEY = "parksmart-pending-intent";

function savePendingIntent(intent: PendingIntent) {
  sessionStorage.setItem(PENDING_INTENT_KEY, JSON.stringify(intent));
}

function takePendingIntent(): PendingIntent | null {
  const raw = sessionStorage.getItem(PENDING_INTENT_KEY);
  sessionStorage.removeItem(PENDING_INTENT_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as PendingIntent;
  } catch {
    return null;
  }
}

export default function Home() {
  const router = useRouter();
  const { status, profile } = useAuth();

  useEffect(() => {
    if (status === "authenticated" && profile?.role === "admin") {
      router.replace("/admin");
    }
  }, [profile, router, status]);

  if (status === "loading") {
    return (
      <main className={authStyles.guardState} role="status">
        <div className={authStyles.guardCard}>
          <strong>ParkSmart AI</strong>
          <p>Dang xac minh phien dang nhap...</p>
        </div>
      </main>
    );
  }

  if (status !== "authenticated" || !profile) return <GuestPreview />;
  if (profile.role !== "user") return null;

  const identity = parkingIdentityFromProfile(profile);
  if (!identity) return null;
  return <ParkSmartUserApp identity={identity} />;
}

function GuestPreview() {
  const router = useRouter();
  const [chatText, setChatText] = useState("");

  function gate(intent: PendingIntent) {
    savePendingIntent(intent);
    router.push("/login");
  }

  return (
    <main className="chat-app-shell">
      <header className="chat-app-header">
        <div className="chat-brand" aria-label="ParkSmart AI">
          <span className="brand-mark" aria-hidden="true">P</span>
          <strong>ParkSmart<span>AI</span></strong>
        </div>
        <button type="button" className="secondary-button" onClick={() => router.push("/login")}>
          Dang nhap
        </button>
      </header>
      <section className="chat-workspace" aria-label="ParkSmart preview">
        <div className="chat-conversation" aria-live="polite">
          <div className="conversation-intro">
            <span className="agent-avatar" aria-hidden="true">AI</span>
            <div>
              <h1>Tro ly ParkSmart</h1>
              <p>Ban dang xem ban xem truoc. Dang nhap de dung du lieu bai xe that.</p>
            </div>
          </div>
          <article className="chat-message message-agent">
            <div className="message-card">
              <p>Toi co the giup tim cho do, xac nhan vi tri, tim xe va gui bao cao.</p>
              <small>ParkSmart AI</small>
            </div>
            <div className="conversation-actions">
              <button type="button" onClick={() => gate({ type: "find-parking" })}>Tim o do</button>
              <button type="button" onClick={() => gate({ type: "find-vehicle" })}>Tim xe</button>
              <button type="button" onClick={() => gate({ type: "location" })}>Xac nhan vi tri</button>
              <button type="button" onClick={() => gate({ type: "report" })}>Bao xe do sai</button>
            </div>
          </article>
        </div>
        <footer className="chat-composer-dock">
          <form
            className="agent-composer"
            onSubmit={(event) => {
              event.preventDefault();
              const message = chatText.trim();
              if (message) gate({ type: "chat", message });
            }}
          >
            <input
              value={chatText}
              onChange={(event) => setChatText(event.target.value)}
              placeholder="Nhap tin nhan..."
            />
            <button type="submit">Gui</button>
          </form>
        </footer>
      </section>
    </main>
  );
}

function ParkSmartUserApp({
  identity,
}: {
  identity: { userId: string; vehicleId: string | null };
}) {
  const { refreshProfile } = useAuth();
  const data = useParkSmartData(parkSmartApi, identity.userId);
  const workflow = useParkingWorkflow(data, parkSmartApi, identity);
  const [manualLocationPicker, setManualLocationPicker] = useState(false);
  const [manualReportDialog, setManualReportDialog] = useState(false);
  const [vehicleGateOpen, setVehicleGateOpen] = useState(false);
  const [pendingVehicleIntent, setPendingVehicleIntent] =
    useState<VehiclePendingIntent | null>(null);
  const pendingVehicleIntentRef = useRef<VehiclePendingIntent | null>(null);

  const showLocationPicker =
    manualLocationPicker || workflow.requestedPanel?.kind === "location";
  const showReportDialog =
    manualReportDialog ||
    workflow.requestedPanel?.kind === "wrong-parking-report";
  const routeInstructions = workflow.activeRoute
    ? buildRouteInstructions(workflow.activeRoute, data.map)
    : [];
  const currentLocationIsParkingSlot = data.slots.some(
    (slot) => slot.id === workflow.currentLocationId,
  );
  const initialReportSlotId =
    (workflow.requestedPanel?.kind === "wrong-parking-report"
      ? workflow.requestedPanel.slotId
      : null) ??
    (currentLocationIsParkingSlot ? workflow.currentLocationId : null) ??
    workflow.selectedSlotId;
  const reservationLocationMatches =
    data.activeReservation?.slot_id === workflow.currentLocationId;

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
      user_id: identity.userId,
      slot_id: draft.slotId,
      reason_code: draft.reasonCode,
      observed_plate_number: draft.observedPlateNumber,
      description: draft.description,
      evidence: draft.evidence,
    });
    notifyWrongParkingReportCreated();
  }

  function requireVehicle(intent: VehiclePendingIntent) {
    if (identity.vehicleId) return true;
    pendingVehicleIntentRef.current = intent;
    setPendingVehicleIntent(intent);
    setVehicleGateOpen(true);
    return false;
  }

  async function resumeIntent(intent: PendingIntent) {
    if (intent.type === "find-parking") {
      await workflow.requestRecommendations({
        chargingRequired: false,
        accessibleRequired: false,
        nearElevator: false,
      });
    } else if (intent.type === "find-vehicle") {
      if (requireVehicle(intent)) await workflow.findVehicleAndRoute();
    } else if (intent.type === "location") {
      setManualLocationPicker(true);
    } else if (intent.type === "report") {
      setManualReportDialog(true);
    } else if (intent.type === "chat") {
      await workflow.sendAgentMessage(intent.message);
    }
  }

  useEffect(() => {
    if (!workflow.threadId) return;
    const intent = takePendingIntent();
    if (!intent) return;
    const timer = window.setTimeout(() => void resumeIntent(intent), 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflow.threadId]);

  async function resumeVehicleIntent(intent: VehiclePendingIntent) {
    if (intent.type === "find-vehicle") {
      await workflow.findVehicleAndRoute();
    } else if (intent.type === "reserve-and-route") {
      await workflow.reserveSelectedAndRoute(intent.slotId);
    } else if (intent.type === "confirm-parking") {
      await workflow.confirmParking();
    } else if (intent.type === "complete-session") {
      await workflow.completeSession();
    } else if (intent.type === "ui-action") {
      await workflow.executeUiAction(intent.messageId, intent.action);
    }
  }

  useEffect(() => {
    if (!identity.vehicleId) return;
    const intent = pendingVehicleIntent ?? pendingVehicleIntentRef.current;
    if (!intent) return;
    pendingVehicleIntentRef.current = null;
    setPendingVehicleIntent(null);
    void resumeVehicleIntent(intent);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [identity.vehicleId, pendingVehicleIntent]);

  async function gatedUiAction(messageId: string, action: ChatUiAction) {
    if (
      ["FIND_VEHICLE", "RESERVE_AND_ROUTE", "CONFIRM_PARKING", "COMPLETE_SESSION"].includes(
        action.type,
      ) &&
      !requireVehicle({ type: "ui-action", messageId, action })
    ) {
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
        <div className={authStyles.userHeaderActions}>
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
          <LogoutButton />
        </div>
      </header>

      <section className="chat-workspace" aria-label="Trò chuyện với ParkSmart">
        <div className="chat-conversation" aria-live="polite">
          <div className="conversation-intro">
            <span className="agent-avatar" aria-hidden="true">AI</span>
            <div>
              <h1>Trợ lý ParkSmart</h1>
              <p>{workflow.threadId ? "Sẵn sàng hỗ trợ" : "Đang khởi tạo..."}</p>
            </div>
          </div>

          {data.loading && (
            <p className="conversation-system-status" role="status">
              Đang đồng bộ thông tin của bạn...
            </p>
          )}
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
              <button
                type="button"
                onClick={() => {
                  if (requireVehicle({ type: "confirm-parking" })) {
                    void workflow.confirmParking();
                  }
                }}
                disabled={workflow.pending === "confirm-parking"}
              >
                {workflow.pending === "confirm-parking"
                  ? reservationLocationMatches
                    ? "Đang xác nhận..."
                    : "Đang xác nhận đến nơi..."
                  : reservationLocationMatches
                    ? "Xác nhận đã đỗ"
                    : "Tôi đã đến nơi"}
              </button>
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
                    onClick={() => {
                      if (requireVehicle({ type: "find-vehicle" })) {
                        void workflow.findVehicleAndRoute();
                      }
                    }}
                    disabled={workflow.pending === "find-car"}
                  >
                    Chỉ đường tới xe
                  </button>
                  <button
                    type="button"
                    className="danger-text-button"
                    onClick={() => {
                      if (requireVehicle({ type: "complete-session" })) {
                        void workflow.completeSession();
                      }
                    }}
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
                  onAction={gatedUiAction}
                />
              )}
            </article>
          ))}

          {workflow.activeRoute && (
            <article className="conversation-route-card" aria-label="Chỉ đường trong bãi">
              <header>
                <div>
                  <small>CHỈ ĐƯỜNG TRONG BÃI</small>
                  <h2>Đến {formatParkingLocation(workflow.activeRoute.path.at(-1))}</h2>
                </div>
                <strong>{workflow.activeRoute.distance_m} m</strong>
              </header>
              <ol>
                {routeInstructions.map((instruction, index) => (
                  <li key={`${instruction.nodeId}-${index}`}>
                    <span className={`route-instruction-icon route-${instruction.kind.toLowerCase()}`} aria-hidden="true">
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
      {vehicleGateOpen && (
        <FirstVehicleDialog
          onClose={() => setVehicleGateOpen(false)}
          onCreated={async () => {
            const intent = pendingVehicleIntentRef.current ?? pendingVehicleIntent;
            setVehicleGateOpen(false);
            await refreshProfile();
            if (intent) {
              pendingVehicleIntentRef.current = intent;
              setPendingVehicleIntent(intent);
            }
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
      setError(formatApiErrorForOperator(submitError, "Khong the them xe."));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => !pending && onClose()}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="first-vehicle-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button type="button" className="modal-close" onClick={onClose} disabled={pending}>
          x
        </button>
        <h2 id="first-vehicle-title">Them xe dau tien</h2>
        <label>
          Bien so
          <input
            value={plateNumber}
            onChange={(event) => setPlateNumber(event.target.value.toUpperCase())}
            maxLength={32}
            disabled={pending}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={requiresCharging}
            onChange={(event) => setRequiresCharging(event.target.checked)}
            disabled={pending}
          />
          Xe can sac dien
        </label>
        {error && <p className="report-error" role="alert">{error}</p>}
        <button
          type="button"
          className="primary-button"
          disabled={pending || plateNumber.trim().length < 2}
          onClick={() => void submit()}
        >
          {pending ? "Dang them..." : "Them xe"}
        </button>
      </section>
    </div>
  );
}
