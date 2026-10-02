import { useCallback, useEffect, useState } from "react";

export function useQuery<T>(loader: () => Promise<T>) {
  const [data, setData] = useState<T>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    void loader().then((value) => { if (active) setData(value); }).catch((error: unknown) => { if (active) setError(error instanceof Error ? error.message : "요청을 처리하지 못했습니다."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [loader, revision]);
  return { data, loading, error, reload };
}
