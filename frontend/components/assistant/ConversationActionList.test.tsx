import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WorkflowMessage } from "@/hooks/use-parking-workflow";
import type { ChatUiAction } from "@/lib/types";

import { ConversationActionList } from "./ConversationActionList";

afterEach(cleanup);

const action: ChatUiAction = {
  id: "reserve-and-route:f1-d01",
  type: "RESERVE_AND_ROUTE",
  label: "Giữ ô và chỉ đường",
  payload: { slot_id: "F1-D01" },
  style: "primary",
  requires_confirmation: true,
};

function message(overrides: Partial<WorkflowMessage> = {}): WorkflowMessage {
  return {
    id: "agent-1",
    role: "agent",
    text: "Bạn muốn giữ ô này?",
    uiActions: [action],
    consumedActionIds: [],
    ...overrides,
  };
}

describe("ConversationActionList", () => {
  it("provides an accessible action name and delegates through the workflow callback", async () => {
    const user = userEvent.setup();
    const onAction = vi.fn(async () => undefined);
    render(
      <ConversationActionList
        message={message()}
        pending={false}
        onAction={onAction}
      />,
    );

    await user.click(
      screen.getByRole("button", {
        name: "Giữ ô và chỉ đường, thao tác cần xác nhận",
      }),
    );
    expect(onAction).toHaveBeenCalledWith("agent-1", action);
  });

  it("disables a consumed action with a textual status", () => {
    render(
      <ConversationActionList
        message={message({ consumedActionIds: [action.id] })}
        pending={false}
        onAction={vi.fn()}
      />,
    );

    const button = screen.getByRole("button", { name: /đã sử dụng/ });
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("Đã dùng");
  });

  it("renders at most five actions", () => {
    render(
      <ConversationActionList
        message={message({
          uiActions: Array.from({ length: 7 }, (_, index) => ({
            ...action,
            id: `action-${index}`,
            label: `Action ${index}`,
          })),
        })}
        pending={false}
        onAction={vi.fn()}
      />,
    );
    expect(screen.getAllByRole("button")).toHaveLength(5);
  });
});
