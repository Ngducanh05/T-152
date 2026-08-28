import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentMessageContent } from "./AgentMessageContent";

describe("AgentMessageContent", () => {
  it("renders Markdown emphasis and list content without raw Markdown markers", () => {
    render(<AgentMessageContent content={"**118 ô trống**\n\n- Khu A: 29 ô"} />);
    expect(screen.getByText("118 ô trống").tagName).toBe("STRONG");
    expect(screen.getByRole("list")).toHaveTextContent("Khu A: 29 ô");
  });

  it("safely renders a Markdown table fallback", () => {
    render(<AgentMessageContent content={"| Khu | Số ô |\n| --- | --- |\n| A | 29 |"} />);
    expect(screen.getByRole("table")).toHaveTextContent("Khu");
    expect(screen.getByRole("table")).toHaveTextContent("29");
  });
});
