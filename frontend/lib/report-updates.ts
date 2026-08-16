const WRONG_PARKING_REPORT_CHANNEL = "parksmart-wrong-parking-reports";

type ReportUpdateMessage = {
  type: "wrong-parking-report-created";
};

export function notifyWrongParkingReportCreated(): void {
  if (
    typeof window === "undefined" ||
    typeof window.BroadcastChannel !== "function"
  ) {
    return;
  }

  const channel = new BroadcastChannel(WRONG_PARKING_REPORT_CHANNEL);
  channel.postMessage({ type: "wrong-parking-report-created" } satisfies ReportUpdateMessage);
  channel.close();
}

export function subscribeToWrongParkingReportUpdates(
  onUpdate: () => void,
): () => void {
  if (
    typeof window === "undefined" ||
    typeof window.BroadcastChannel !== "function"
  ) {
    return () => undefined;
  }

  const channel = new BroadcastChannel(WRONG_PARKING_REPORT_CHANNEL);
  channel.addEventListener("message", (event: MessageEvent<unknown>) => {
    const message = event.data as Partial<ReportUpdateMessage> | null;
    if (message?.type === "wrong-parking-report-created") onUpdate();
  });
  return () => channel.close();
}
