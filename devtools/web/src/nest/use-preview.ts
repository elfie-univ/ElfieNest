import { useEffect, useState, type RefObject } from "react";
import { previewCatalogSchema, type CameraCommand, type PreviewCatalog } from "./preview-contracts";
import type { NestEnvironment } from "./contracts";

export function usePreview(frame: RefObject<HTMLIFrameElement | null>, url: string | null, environment: NestEnvironment | null = null) {
  const [catalog, setCatalog] = useState<PreviewCatalog | null>(null);
  useEffect(() => {
    if (environment === null) return;
    frame.current?.contentWindow?.postMessage({ channel: "elfienest-nest-lab", type: "camera", action: "environment", environment }, window.location.origin);
  }, [frame, environment]);
  useEffect(() => {
    setCatalog(null);
    const receive = (event: MessageEvent<unknown>) => {
      if (event.origin !== window.location.origin || event.source !== frame.current?.contentWindow) return;
      let data: unknown = event.data;
      if (typeof data === "string") {
        try { data = JSON.parse(data) as unknown; } catch { return; }
      }
      const parsed = previewCatalogSchema.safeParse(data);
      if (parsed.success) setCatalog(parsed.data);
    };
    const request = () => frame.current?.contentWindow?.postMessage(
      { channel: "elfienest-nest-lab", type: "catalog" }, window.location.origin,
    );
    window.addEventListener("message", receive);
    const timer = window.setInterval(request, 1_500);
    request();
    return () => { window.clearInterval(timer); window.removeEventListener("message", receive); };
  }, [frame, url]);

  function send(command: CameraCommand): void {
    frame.current?.contentWindow?.postMessage(
      { channel: "elfienest-nest-lab", type: "camera", ...command }, window.location.origin,
    );
  }
  return { catalog, send };
}
