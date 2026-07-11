"use client";

import { useEffect, useRef } from "react";
import type { SessionEvent } from "@/lib/types";

const agentColors: Record<string, string> = {
  functional: "text-violet-500",
  security: "text-coral",
  architect: "text-action-blue",
  devops: "text-enterprise-green",
  sre: "text-enterprise-green",
  gemma: "text-violet-400",
  intake: "text-ink-muted",
};

export function EventStream({ events }: { events: SessionEvent[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="flex h-[min(420px,50vh)] flex-col rounded-2xl border border-hairline bg-[#0f0f12]">
      <div className="border-b border-white/10 px-4 py-3">
        <p className="font-mono-label text-[11px] uppercase text-white/50">
          Agent activity
        </p>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4 font-mono text-[12px] leading-relaxed sm:text-[13px]">
        {events.length === 0 && (
          <p className="text-white/40">Waiting for events...</p>
        )}
        {events.map((event, i) => (
          <div key={`${event.timestamp ?? i}-${i}`} className="text-white/85">
            <span className="text-white/35">
              {event.timestamp
                ? new Date(event.timestamp).toLocaleTimeString()
                : "--:--:--"}
            </span>{" "}
            {event.agent && (
              <span
                className={`font-semibold ${agentColors[event.agent] ?? "text-white/70"}`}
              >
                [{event.agent}]
              </span>
            )}{" "}
            {event.message}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
