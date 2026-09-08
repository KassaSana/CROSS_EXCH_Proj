import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { RenderProfile } from "./components/RenderProfile";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RenderProfile id="App"><App /></RenderProfile>
  </React.StrictMode>,
);
