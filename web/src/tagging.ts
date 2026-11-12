import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api } from "./api";
import type { JobDetail, Tag } from "./types";

export type TagBody = { tag: Tag | null; event_date?: string; note?: string };

/** PUT a job's tag (the same call the detail panel's buttons make) and refresh what shows it. */
export function useTagJob() {
  const qc = useQueryClient();
  return useCallback(
    async (id: number, body: TagBody) => {
      const d = await api<JobDetail>(`/api/jobs/${id}/tag`, { method: "PUT", json: body });
      qc.setQueryData(["job", id], d);
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      return d;
    },
    [qc],
  );
}
