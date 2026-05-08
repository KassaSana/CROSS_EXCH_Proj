import { useEffect } from "react";

type MessageHandler = (event: MessageEvent<string>) => void;

export function useWebSocket(handler: MessageHandler): void {
  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/live`);
    socket.onmessage = handler;
    socket.onopen = () => socket.send("dashboard_connected");
    return () => socket.close();
  }, [handler]);
}
