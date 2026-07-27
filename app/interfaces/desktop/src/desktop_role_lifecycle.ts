export const DESKTOP_UI_INSTANCE_NAMESPACE = "elfienest.desktop-ui";
export const GODOT_AUTHORITY_INSTANCE_NAMESPACE = "elfienest.godot-authority";

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
  stopOwnedRuntime(ownerLease: string): Promise<void>;
}

export class DesktopRoleController {
  private currentState: DesktopRoleState = { kind: "stopped" };

  constructor(private readonly lifecycleClient: LifecycleClient) {}

  get state(): DesktopRoleState {
    return this.currentState;
  }

  async start(): Promise<DesktopRoleState> {
    this.currentState = await this.lifecycleClient.attachOrStart();
    return this.currentState;
  }

  async closeWindow(): Promise<void> {
    // Closing an observer window intentionally has no lifecycle side effect.
  }

  async exitApplication(): Promise<void> {
    if (this.currentState.kind === "owned") {
      await this.lifecycleClient.stopOwnedRuntime(this.currentState.ownerLease);
    }
    this.currentState = { kind: "stopped" };
  }
}
