import type { IncidentStatus, Severity } from "../contracts/types";

export const statusLabels: Record<IncidentStatus, string> = { DETECTED: "감지됨", TRIAGED: "초기 분류", INVESTIGATING: "조사 중", RCA_READY: "원인 분석 완료", ACTION_PROPOSED: "조치 제안됨", PENDING_APPROVAL: "승인 대기", EXECUTING: "조치 실행 중", VERIFYING: "검증 중", RESOLVED: "해결됨", CLOSED: "종료", ESCALATED: "상위 이관", BLOCKED: "보류", FAILED: "실패", REOPENED: "재조사" };
export const severityLabels: Record<Severity, string> = { LOW: "낮음", MEDIUM: "보통", HIGH: "높음", CRITICAL: "긴급" };
export const dateTime = (value?: string) => !value || Number.isNaN(Date.parse(value)) ? "기록 없음" : new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
export function ageLabel(value: string, asOf: string) { const minutes = Math.max(0, Math.floor((Date.parse(asOf) - Date.parse(value)) / 60000)); return minutes < 60 ? `${minutes}분` : minutes < 1440 ? `${Math.floor(minutes / 60)}시간 ${minutes % 60}분` : `${Math.floor(minutes / 1440)}일`; }
export const percent = (value: number) => `${Math.round(value * 100)}%`;
