"use client";

import type { WorkflowMessage } from "@/hooks/use-parking-workflow";
import type { ChatUiAction } from "@/lib/types";

interface ConversationActionListProps {
  message: WorkflowMessage;
  pending: boolean;
  onAction: (messageId: string, action: ChatUiAction) => Promise<void>;
}

export function ConversationActionList({
  message,
  pending,
  onAction,
}: ConversationActionListProps) {
  const actions = message.uiActions
    .filter((action) => !message.consumedActionIds.includes(action.id))
    .slice(0, 5);
  if (actions.length === 0) return null;

  return (
    <div
      className="conversation-actions"
      role="group"
      aria-label="Thao tác cho câu trả lời này"
    >
      {actions.map((action) => {
        const accessibleName = `${action.label}${
          action.requires_confirmation ? ", thao tác cần xác nhận" : ""
        }`;
        return (
          <button
            key={action.id}
            type="button"
            className={`conversation-action action-${action.style}`}
            data-slot-id={
              "slot_id" in action.payload ? action.payload.slot_id : undefined
            }
            aria-label={accessibleName}
            disabled={pending}
            onClick={() => void onAction(message.id, action)}
          >
            <span>{action.label}</span>
            {action.requires_confirmation && <small>Chạm để xác nhận</small>}
          </button>
        );
      })}
      <span className="sr-only" role="status" aria-live="polite">
        {pending ? "Đang xử lý thao tác." : ""}
      </span>
    </div>
  );
}
