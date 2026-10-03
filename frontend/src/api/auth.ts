// 개발 계정의 역할·조직은 서버 설정에서 결정하며 임의 헤더로 전달하지 않습니다.
export function authHeaders(): Record<string, string> {
  const token = import.meta.env.DEV ? import.meta.env.VITE_LOCAL_AUTH_TOKEN : undefined;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function commandKey() { return crypto.randomUUID(); }
