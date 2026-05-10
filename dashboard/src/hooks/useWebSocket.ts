import { useEffect, useRef } from "react";
import { WS_BASE } from "../api/client";

type MessageHandler = (event: MessageEvent<string>) => void;

export function useWebSocket(handler: MessageHandler): void {
  const handlerRef = useRef(handler);

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    const socket = new WebSocket(`${WS_BASE}/ws/live`);
    socket.onmessage = (event) => handlerRef.current(event);
    socket.onopen = () => socket.send("dashboard_connected");
    return () => socket.close();
  }, []);
}
