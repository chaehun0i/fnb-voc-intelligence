import { describe, expect, it } from "vitest";
import { ageLabel, dateTime } from "./display";

describe("운영 화면 날짜 표시", () => {
  it("검증 시각이 없거나 잘못되어도 화면을 중단하지 않는다", () => {
    expect(dateTime(undefined)).toBe("기록 없음");
    expect(dateTime("")).toBe("기록 없음");
    expect(dateTime("잘못된 시각")).toBe("기록 없음");
  });
  it("시간대가 있는 시각을 한국 시간으로 표시한다", () => {
    expect(dateTime("2026-10-02T00:00:00Z")).toContain("09:00");
    expect(ageLabel("2026-10-02T00:00:00Z", "2026-10-02T02:15:00Z")).toBe("2시간 15분");
  });
});
