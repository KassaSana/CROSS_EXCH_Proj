import { useEffect } from "react";
import { WS_BASE } from "../api/client";

type MessageHandler = (event: MessageEvent<string>) => void;

export function useWebSocket(handler: MessageHandler): void {
  useEffect(() => {
    const socket = new WebSocket(`${WS_BASE}/ws/live`);
    socket.onmessage = handler;
    socket.onopen = () => socket.send("dashboard_connected");
    return () => socket.close();
  }, [handler]);
}
