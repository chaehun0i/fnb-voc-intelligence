import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

function Bootstrap() { return <main className="bootstrap">ServIQ loading…</main>; }

createRoot(document.getElementById("root")!).render(<StrictMode><Bootstrap /></StrictMode>);
