import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { App } from "./App";

describe("ServIQ app", () => { it("renders operations navigation", () => { render(<App />); expect(screen.getByText("Operations Dashboard")).toBeInTheDocument(); expect(screen.getByText("Incidents")).toBeInTheDocument(); expect(screen.getByText("Agent Trace")).toBeInTheDocument(); expect(screen.getByText("Settings")).toBeInTheDocument(); }); });
