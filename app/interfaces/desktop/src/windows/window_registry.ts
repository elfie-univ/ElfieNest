export type ManagedWindow = Readonly<{
  isDestroyed(): boolean;
}>;

export class SingleWindowRegistry<TWindow extends ManagedWindow> {
  private window: TWindow | undefined;

  current(): TWindow | undefined {
    if (this.window?.isDestroyed() === true) {
      this.window = undefined;
    }
    return this.window;
  }

  ensure(create: () => TWindow): Readonly<{ window: TWindow; created: boolean }> {
    const current = this.current();
    if (current !== undefined) {
      return { window: current, created: false };
    }
    const window = create();
    this.window = window;
    return { window, created: true };
  }

  clear(window: TWindow): void {
    if (this.window === window) {
      this.window = undefined;
    }
  }
}
