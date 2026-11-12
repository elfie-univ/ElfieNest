import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";

import { requestJson } from "../api/http";
import { prepareNestPreview } from "./prepare-preview";
import {
  actorsSchema,
  environmentSchema, type NestEnvironment,
  actorSpeciesSchema,
  type ActorSpecies,
  eventsSchema,
  godotWebSchema,
  runtimeSchema,
  targetsSchema,
  type NestTarget,
  type NestActor,
  type NestEvent,
  type NestRuntime,
  type NestWorld,
  worldSchema,
} from "./contracts";

type NestLabState = Readonly<{
  readonly environment: NestEnvironment | null;
  readonly runtime: NestRuntime | null;
  readonly world: NestWorld | null;
  readonly species: readonly ActorSpecies[];
  readonly actors: readonly NestActor[];
  readonly targets: readonly NestTarget[];
  readonly events: readonly NestEvent[];
  readonly previewUrl: string | null;
  readonly previewHint: string | null;
}>;

const initialState: NestLabState = {
  environment: null,
  runtime: null,
  world: null,
  actors: [],
  species: [],
  targets: [],
  events: [],
  previewUrl: null,
  previewHint: null,
};

export function useNestLab(): Readonly<{
  readonly state: NestLabState;
  readonly error: string | null;
  readonly refresh: () => Promise<void>;
  readonly run: (path: string, method: "post" | "put" | "delete", json?: unknown) => Promise<unknown>;
}> {
  const [state, setState] = useState<NestLabState>(initialState);
  const [error, setError] = useState<string | null>(null);
  const live = useRef(true);

  const refresh = useCallback(async (): Promise<void> => {
    const [runtime, world, actors, events, bundle, targets, species, environment] = await Promise.all([
      requestJson("runtime", runtimeSchema),
      requestJson("world", worldSchema),
      requestJson("actors", actorsSchema),
      requestJson("events", eventsSchema),
      requestJson("godot-web", godotWebSchema),
      requestJson("action-targets", targetsSchema),
      requestJson("actor-species", actorSpeciesSchema),
      requestJson("environment", environmentSchema),
    ]);
    if (!live.current) return;
    const query = new URLSearchParams({
      ws: runtime.websocket_url,
      nonce: runtime.nonce,
      mode: "authority",
      lab: "nest_lab",
    });
    setState({
      environment,
      runtime,
      world,
      species: species.items,
      actors: actors.items,
      targets: targets.items,
      events: events.items,
      previewUrl: bundle.ready ? `${bundle.entry_url}?${query.toString()}` : null,
      previewHint: bundle.ready ? null : `未找到导出物：${bundle.build_command}`,
    });
    setError(null);
  }, []);

  const run = useCallback(
    async (path: string, method: "post" | "put" | "delete", json?: unknown): Promise<unknown> => {
      const result = await requestJson(path, z.unknown(), { method, json });
      await refresh();
      return result;
    },
    [refresh],
  );

  useEffect(() => {
    live.current = true;
    const controller = new AbortController();
    let interval: number | undefined;
    void (async () => {
      await prepareNestPreview(controller.signal);
      if (controller.signal.aborted) return;
      await refresh();
      if (controller.signal.aborted) return;
      interval = window.setInterval(() => {
        void refresh().catch((reason: unknown) => {
          if (live.current) setError(reason instanceof Error ? reason.message : "刷新失败");
        });
      }, 1_500);
    })().catch((reason: unknown) => {
      if (live.current) setError(reason instanceof Error ? reason.message : "初始化失败");
    });
    return () => {
      live.current = false;
      controller.abort();
      window.clearInterval(interval);
    };
  }, [refresh]);

  return { state, error, refresh, run };
}
