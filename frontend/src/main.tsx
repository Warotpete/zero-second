import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { roomFromUrl, useRoom } from "./api";
import Fan from "./pages/Fan";
import Live from "./pages/Live";
import Memory from "./pages/Memory";
import Recap from "./pages/Recap";
import Trace from "./pages/Trace";
import "./styles.css";

function App() {
  const room = roomFromUrl();
  const snap = useRoom(room);
  if (!snap) {
    return (
      <div style={{ height: "100vh", display: "grid", placeItems: "center" }}>
        <div className="logo"><div className="logo-mark">0″</div>Zero Second · connecting…</div>
      </div>
    );
  }
  const q = window.location.search;
  return (
    <Routes>
      <Route path="/desk" element={<Live snap={snap} room={room} />} />
      <Route path="/desk/trace" element={<Trace snap={snap} room={room} />} />
      <Route path="/desk/recap" element={<Recap snap={snap} room={room} />} />
      <Route path="/desk/memory" element={<Memory snap={snap} room={room} />} />
      <Route path="/fan" element={<Fan snap={snap} room={room} />} />
      <Route path="*" element={<Navigate to={`/desk${q}`} replace />} />
    </Routes>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
