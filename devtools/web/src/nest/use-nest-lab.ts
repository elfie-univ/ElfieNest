import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";

import { requestJson } from "../api/http";
import {
  actorsSchema,
  eventsSchema,
  godotWebSchema,
  runtimeSchema,
  type NestActor,
  type NestEvent,
  type NestRuntime,
  type NestWorld,
  worldSchema,
} from "./contracts";

type NestLabState = Readonly<{
  readonly runtime: NestRuntime | null;
  readonly world: NestWorld | null;
  readonly actors: readonly NestActor[];
  readonly events: readonly NestEvent[];
  readonly previewUrl: string | null;
  readonly previewHint: string | null;
}>;

const initialState: NestLabState = {
  runtime: null,
  world: null,
  actors: [],
  events: [],
  previewUrl: null,
  previewHint: null,
};

export function useNestLab(): Readonly<{
  readonly state: NestLabState;
  readonly error: string | null;
  readonly refresh: () => Promise<void>;
  readonly run: (path: string, method: "post" | "put", json?: unknown) => Promise<void>;
}> {
  const [state, setState] = useState<NestLabState>(initialState);
  const [error, setError] = useState<string | null>(null);
  const live = useRef(true);

  const refresh = useCallback(async (): Promise<void> => {
    const [runtime, world, actors, events, bundle] = await Promise.all([
      requestJson("runtime", runtimeSchema),
      requestJson("world", worldSchema),
      requestJson("actors", actorsSchema),
      requestJson("events", eventsSchema),
      requestJson("godot-web", godotWebSchema),
    ]);
    if (!live.current) return;
    const query = new URLSearchParams({
      ws: runtime.websocket_url,
      nonce: runtime.nonce,
      mode: "nest_lab",
    });
    setState({
      runtime,
      world,
      actors: actors.items,
      events: events.items,
      previewUrl: bundle.ready ? `${bundle.entry_url}?${query.toString()}` : null,
      previewHint: bundle.ready ? null : `未找到导出物：${bundle.build_command}`,
    });
    setError(null);
  }, []);

  const run = useCallback(
    async (path: string, method: "post" | "put", json?: unknown): Promise<void> => {
      await requestJson(path, z.unknown(), { method, json });
      await refresh();
    },
    [refresh],
  );

  useEffect(() => {
    live.current = true;
    void refresh().catch((reason: unknown) => {
      if (live.current) setError(reason instanceof Error ? reason.message : "初始化失败");
    });
    const interval = window.setInterval(() => {
      void refresh().catch((reason: unknown) => {
        if (live.current) setError(reason instanceof Error ? reason.message : "刷新失败");
      });
    }, 1_500);
    return () => {
      live.current = false;
      window.clearInterval(interval);
    };
  }, [refresh]);

  return { state, error, refresh, run };
}
