import { describe, expect, it, vi } from "vitest";
import { createHttpSettingsApi, decodeWorkspace, mockSettingsApi } from "./index";

describe("운영 설정 Adapter", () => {
  it("HTTP current/history/save/rollback을 동일 계약으로 반환한다", async () => {
    const workspace = await mockSettingsApi.current();
    const history = await mockSettingsApi.history();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(JSON.stringify(workspace))).mockResolvedValueOnce(new Response(JSON.stringify(history))).mockImplementation(async () => new Response(JSON.stringify(workspace)));
    const api = createHttpSettingsApi("http://test/api/v1", fetcher);
    expect(await api.current()).toEqual(workspace);
    expect(await api.history()).toEqual(history);
    await api.save(workspace.effective, 1, "변경 사유", "same-key");
    await api.rollback(1, 2, "복원 사유", "rollback-key");
    expect(fetcher.mock.calls[2][1]?.headers).toMatchObject({ "Idempotency-Key": "same-key" });
    expect(JSON.parse(String(fetcher.mock.calls[3][1]?.body))).toMatchObject({ target_version: 1, expected_version: 2 });
  });
  it.each([[401, "AUTHENTICATION_REQUIRED"], [403, "AUTHORIZATION_DENIED"], [409, "VERSION_CONFLICT"], [409, "IDEMPOTENCY_CONFLICT"], [422, "CONFIG_VALIDATION_FAILED"], [503, "SETTINGS_UNAVAILABLE"]])("%s 오류에 request id를 보존하고 Mock으로 대체하지 않는다", async (status, code) => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ error: { code, message: "secret-internal", details: [{ field: "max_tool_calls", reason: "상한 초과" }] }, request_id: "settings-request" }), { status: Number(status) }));
    const api = createHttpSettingsApi("http://test/api/v1", fetcher);
    await expect(api.current()).rejects.toMatchObject({ code, requestId: "settings-request", details: [{ field: "max_tool_calls", reason: "상한 초과" }] });
    await expect(api.current()).rejects.not.toHaveProperty("message", "secret-internal");
  });
  it("계약 오류와 네트워크 실패를 구분한다", async () => {
    expect(() => decodeWorkspace({ config: {} })).toThrow("응답 형식");
    const api = createHttpSettingsApi("http://test", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline")));
    await expect(api.current()).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });
});
