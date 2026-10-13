import { useEffect, useState } from "react";
import { getToken } from "../api/client";

export interface LiveAlert {
  type: string;
  id: string;
  severity: "low" | "medium" | "high" | "critical";
  status: string;
  title: string;
  summary: string;
  context: Record<string, unknown> | null;
  user_id: string;
  created_at: string;
}

/**
 * Live alert feed (admin only). The WS endpoint validates the JWT query param;
 * frames are JSON alert payloads pushed by the Celery dispatcher via Redis
 * pub/sub. Reconnection: React remounts / effect re-run handles the common
 * cases; the DB remains the source of truth if the socket drops.
 */
export function useAlertSocket(enabled: boolean): {
  connected: boolean;
  latest: LiveAlert[];
  dismiss: (id: string) => void;
  clear: () => void;
} {
  const [connected, setConnected] = useState(false);
  const [latest, setLatest] = useState<LiveAlert[]>([]);

  useEffect(() => {
    if (!enabled) return;
    const token = getToken();
    if (!token) return;

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.host}/api/v1/ws/alerts?token=${encodeURIComponent(token)}`;
    let socket: WebSocket;
    try {
      socket = new WebSocket(url);
    } catch {
      return;
    }

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onerror = () => socket.close();
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as LiveAlert;
        if (data?.type === "ping") return;
        setLatest((prev) => [data, ...prev].slice(0, 20));
      } catch {
        /* ignore malformed frames */
      }
    };

    return () => {
      socket.onclose = null;
      socket.close();
      setConnected(false);
    };
  }, [enabled]);

  return {
    connected,
    latest,
    dismiss: (id: string) => setLatest((prev) => prev.filter((a) => a.id !== id)),
    clear: () => setLatest([]),
  };
}
