export type ElectronRole = "desktop-ui" | "godot-authority";

const AUTHORITY_ROLE_ARGUMENT = "--elfienest-role=godot-authority";

export function resolveElectronRole(argumentsList: readonly string[]): ElectronRole {
  return argumentsList.includes(AUTHORITY_ROLE_ARGUMENT)
    ? "godot-authority"
    : "desktop-ui";
}
