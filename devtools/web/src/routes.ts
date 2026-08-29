import type { LabKind } from "./lab-kind";

export const devtoolsRoutes = {
  elfieExperiment: "elfie-experiment",
  elfieEvaluations: "elfie-evaluations",
  nestExperiment: "nest-experiment",
} as const;

export type DevtoolsRoute = (typeof devtoolsRoutes)[keyof typeof devtoolsRoutes];

const routePaths: Readonly<Record<DevtoolsRoute, string>> = {
  [devtoolsRoutes.elfieExperiment]: "/elfie/experiment",
  [devtoolsRoutes.elfieEvaluations]: "/elfie/evaluations",
  [devtoolsRoutes.nestExperiment]: "/nest/experiment",
};

export function routePath(route: DevtoolsRoute): string {
  return routePaths[route];
}

function normalizedPath(pathname: string): string {
  const trimmed = pathname.replace(/\/+$/, "");
  return trimmed || "/";
}

export function routeFromPath(kind: LabKind, pathname: string): DevtoolsRoute {
  const path = normalizedPath(pathname);
  if (kind === "nest") return devtoolsRoutes.nestExperiment;
  if (kind === "unified" && path === "/nest/experiment") {
    return devtoolsRoutes.nestExperiment;
  }
  if (path === "/elfie/evaluations" || path === "/evaluations") {
    return devtoolsRoutes.elfieEvaluations;
  }
  return devtoolsRoutes.elfieExperiment;
}

function serviceOrigin(kind: LabKind, location: Location): string {
  const url = new URL(location.href);
  if (kind === "unified") return url.origin;
  if (kind === "elfie") {
    url.port = "9001";
  } else {
    url.port = "9002";
  }
  return url.origin;
}

export function routeHref(
  route: DevtoolsRoute,
  currentKind: LabKind,
  location: Location = window.location,
): string {
  const targetKind: LabKind = route === devtoolsRoutes.nestExperiment ? "nest" : "elfie";
  const path = routePath(route);
  if (currentKind === "unified") return path;
  if (targetKind === currentKind) return path;
  const origin = serviceOrigin(targetKind, location);
  if (origin === location.origin) return path;
  return `${origin}${path}`;
}
