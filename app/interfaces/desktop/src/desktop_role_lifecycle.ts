export const DESKTOP_UI_INSTANCE_NAMESPACE = "elfienest.desktop-ui";

export type RuntimeAttachment =
  | Readonly<{ readonly kind: "attached"; readonly generation: number }>
  | Readonly<{
      readonly kind: "owned";
      readonly generation: number;
      readonly ownerLease: string;
    }>
  | Readonly<{
      readonly kind: "failed";
      readonly reason: string;
      readonly recoverable: boolean;
    }>;

export type DesktopRoleState = RuntimeAttachment | Readonly<{ readonly kind: "stopped" }>;

export interface LifecycleClient {
  attachOrStart(): Promise<RuntimeAttachment>;
  recoverOwnedRuntime(ownerLease: string): Promise<RuntimeAttachment>;
  stopOwnedRuntime(ownerLease: string): Promise<void>;
}

export class DesktopRoleController {
  private currentState: DesktopRoleState = { kind: "stopped" };
  private startPromise: Promise<RuntimeAttachment> | undefined;

  constructor(private readonly lifecycleClient: LifecycleClient) {}

  get state(): DesktopRoleState {
    return this.currentState;
  }

  async start(): Promise<DesktopRoleState> {
    const pending = this.lifecycleClient.attachOrStart();
    this.startPromise = pending;
    try {
      this.currentState = await pending;
      return this.currentState;
    } finally {
      if (this.startPromise === pending) {
        this.startPromise = undefined;
      }
    }
  }

  async closeWindow(): Promise<void> {
    // Closing an observer window intentionally has no lifecycle side effect.
  }

  async maintainOwnedRuntime(): Promise<DesktopRoleState> {
    if (this.currentState.kind !== "owned") {
      return this.currentState;
    }
    const recovered = await this.lifecycleClient.recoverOwnedRuntime(
      this.currentState.ownerLease,
    );
    if (recovered.kind === "owned") {
      this.currentState = recovered;
    }
    return recovered;
  }

  async exitApplication(): Promise<void> {
    try {
      if (this.startPromise !== undefined) {
        await this.startPromise;
      }
      if (this.currentState.kind === "owned") {
        await this.lifecycleClient.stopOwnedRuntime(this.currentState.ownerLease);
      }
    } finally {
      // The Desktop process is leaving regardless of whether the public stop
      // command succeeded. Never leave the controller in an owned state after
      // an explicit quit has been requested.
      this.currentState = { kind: "stopped" };
    }
  }
}
