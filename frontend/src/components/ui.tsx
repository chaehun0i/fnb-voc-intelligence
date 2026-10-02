import type { ButtonHTMLAttributes, ReactNode } from "react";
import { AlertCircle, Inbox, LoaderCircle } from "lucide-react";

export function Button({ children, className = "", variant = "secondary", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  return <button {...props} className={`ui-button ${variant} ${className}`}>{children}</button>;
}
export function PageHeading({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
  return <div className="page-heading"><div><h1>{title}</h1><p>{description}</p></div>{children}</div>;
}
export function StateMessage({ kind = "empty", title, children, onRetry }: { kind?: "loading" | "empty" | "error"; title: string; children?: ReactNode; onRetry?: () => void }) {
  const Icon = kind === "loading" ? LoaderCircle : kind === "error" ? AlertCircle : Inbox;
  return <div className={`state-message ${kind}`} role={kind === "error" ? "alert" : "status"}><div><Icon size={26} className={kind === "loading" ? "animate-spin" : ""} /><strong>{title}</strong>{children && <p>{children}</p>}{onRetry && <Button onClick={onRetry}>다시 불러오기</Button>}</div></div>;
}
export function StatCard({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return <div className="summary-card"><span>{label}</span><strong>{value}</strong>{hint && <small className="muted">{hint}</small>}</div>;
}
export function PreviewNotice() { return <p className="preview-notice">미리보기 데이터 · 검토와 설정 변경은 이 브라우저 세션에만 반영됩니다.</p>; }
