"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function AgentMessageContent({ content }: { content: string }) {
  return (
    <div className="agent-message-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
