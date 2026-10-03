import type { DashboardSnapshot } from "../../contracts/types";
import { mockApi } from "../mockApi";

export interface DashboardApi {
  getSnapshot(): Promise<DashboardSnapshot>;
}

// 예시도 하나의 Snapshot 계약을 사용하며 실제 HTTP 경로와 합치지 않습니다.
export const mockDashboardApi: DashboardApi = {
  getSnapshot: () => mockApi.getDashboardSnapshot(),
};
