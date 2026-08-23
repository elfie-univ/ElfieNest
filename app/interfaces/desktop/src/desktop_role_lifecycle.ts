import type {
  DataHomeInspection,
  DataHomeRecoveryResult,
  RuntimeStartupPhase,
} from "./lifecycle_client.js";

export const DESKTOP_UI_INSTANCE_NAMESPACE = "elfienest.desktop-ui";

export type RuntimeAttachment =
  | Readonly<{
      readonly kind: "attached";
      readonly generation: number;
      readonly dataHome: string;
      readonly httpUrl?: string;
    }>
  | Readonly<{
      readonly kind: "owned";
      readonly generation: number;
      readonly ownerLease: string;
      readonly dataHome: string;
      readonly httpUrl?: string;
    }>
  | Readonly<{
      readonly kind: "failed";
      readonly reason: string;
      readonly recoverable: boolean;
      readonly recovery?: DataHomeInspection;
    }>;

export type DesktopRoleState = RuntimeAttachment | Readonly<{ readonly kind: "stopped" }>;

export interface LifecycleClient {
  inspectDataHome(explicitHome?: string): Promise<DataHomeInspection>;
  recoverDataHome(explicitHome?: string): Promise<DataHomeRecoveryResult>;
  attachOrStart(onProgress?: (phase: RuntimeStartupPhase) => void): Promise<RuntimeAttachment>;
  recoverOwnedRuntime(ownerLease: string): Promise<RuntimeAttachment>;
  stopOwnedRuntime(ownerLease: string): Promise<void>;
  cancelStart(): Promise<void>;
}

export class DesktopRoleController {
  private currentState: DesktopRoleState = { kind: "stopped" };
  private startPromise: Promise<RuntimeAttachment> | undefined;
  private maintenancePromise: Promise<DesktopRoleState> | undefined;
  private lastRecoveryResult: DataHomeRecoveryResult | undefined;
  private ownedRuntimeForExit: Extract<RuntimeAttachment, { readonly kind: "owned" }> | undefined;
  private exitRequested = false;

  constructor(private readonly lifecycleClient: LifecycleClient) {}

  get state(): DesktopRoleState {
    return this.currentState;
  }

  get lastRecovery(): DataHomeRecoveryResult | undefined {
    return this.lastRecoveryResult;
  }

  async start(
    onProgress?: (phase: RuntimeStartupPhase) => void,
  ): Promise<DesktopRoleState> {
    if (this.exitRequested) {
      return { kind: "stopped" };
    }
    const existingStart = this.startPromise;
    if (existingStart !== undefined) {
      this.currentState = await existingStart;
      this.rememberOwnedRuntime(this.currentState);
      return this.currentState;
    }
    const pending = (async (): Promise<RuntimeAttachment> => {
      const inspection = await this.lifecycleClient.inspectDataHome();
      if (
        inspection.state !== "fresh"
        && inspection.state !== "partial"
        && inspection.state !== "ready"
      ) {
        return {
          kind: "failed",
          reason: inspection.detail,
          recoverable: inspection.recoverable,
          ...(inspection.recoverable ? { recovery: inspection } : {}),
        };
      }
      return this.lifecycleClient.attachOrStart(onProgress);
    })();
    this.startPromise = pending;
    try {
      const state = await pending;
      if (this.exitRequested) {
        this.currentState = { kind: "stopped" };
        return this.currentState;
      }
      this.currentState = state;
      this.rememberOwnedRuntime(state);
      return this.currentState;
    } finally {
      if (this.startPromise === pending) {
        this.startPromise = undefined;
      }
    }
  }

  async recoverDataHome(
    onProgress?: (phase: RuntimeStartupPhase) => void,
  ): Promise<DesktopRoleState> {
    try {
      this.lastRecoveryResult = await this.lifecycleClient.recoverDataHome();
    } catch (error: unknown) {
      this.currentState = {
        kind: "failed",
        reason: error instanceof Error ? error.message : "Data-root recovery failed",
        recoverable: true,
      };
      return this.currentState;
    }
    return this.start(onProgress);
  }

  async closeWindow(): Promise<void> {
    // Closing an observer window intentionally has no lifecycle side effect.
  }

  async ensureRuntime(
    onProgress?: (phase: RuntimeStartupPhase) => void,
  ): Promise<DesktopRoleState> {
    if (this.startPromise !== undefined) {
      this.currentState = await this.startPromise;
    }
    if (this.currentState.kind === "owned") {
      return this.maintainOwnedRuntime();
    }
    return this.start(onProgress);
  }

  async maintainOwnedRuntime(): Promise<DesktopRoleState> {
    const existingMaintenance = this.maintenancePromise;
    if (existingMaintenance !== undefined) {
      return existingMaintenance;
    }
    if (this.currentState.kind !== "owned") {
      return this.currentState;
    }
    const ownerLease = this.currentState.ownerLease;
    const pending = (async (): Promise<DesktopRoleState> => {
      const recovered = await this.lifecycleClient.recoverOwnedRuntime(ownerLease);
      if (recovered.kind === "failed") {
        this.currentState = recovered;
        return this.currentState;
      }
      if (recovered.kind === "owned") {
        this.currentState = recovered;
        this.rememberOwnedRuntime(recovered);
      }
      return this.currentState;
    })();
    this.maintenancePromise = pending;
    try {
      return await pending;
    } finally {
      if (this.maintenancePromise === pending) {
        this.maintenancePromise = undefined;
      }
    }
  }

  async exitApplication(): Promise<void> {
    let cleanupError: unknown;
    let pendingState: RuntimeAttachment | undefined;
    this.exitRequested = true;
    try {
      if (this.startPromise !== undefined) {
        try {
          await this.lifecycleClient.cancelStart();
        } catch (error: unknown) {
          cleanupError = error;
        }
        try {
          pendingState = await this.startPromise;
        } catch (error: unknown) {
          cleanupError ??= error;
        }
      }
      const ownedState =
        this.currentState.kind === "owned"
          ? this.currentState
          : pendingState?.kind === "owned"
            ? pendingState
            : this.ownedRuntimeForExit;
      if (ownedState !== undefined) {
        await this.lifecycleClient.stopOwnedRuntime(ownedState.ownerLease);
      }
    } finally {
      // The Desktop process is leaving regardless of whether the public stop
      // command succeeded. Never leave the controller in an owned state after
      // an explicit quit has been requested.
      this.currentState = { kind: "stopped" };
      this.ownedRuntimeForExit = undefined;
    }
    if (cleanupError !== undefined) throw cleanupError;
  }

  private rememberOwnedRuntime(state: DesktopRoleState): void {
    if (state.kind === "owned") {
      this.ownedRuntimeForExit = state;
    }
  }
}
