import { app } from "electron";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const AUTHORITY_ROLE_ARGUMENT = "--elfienest-role=godot-authority";
const sourceRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const projectRoot = process.env.ELFIENEST_PROJECT_ROOT ?? sourceRoot;
const packagedRoot = app.getAppPath();
const authorityEntry = app.isPackaged
  ? join(
      packagedRoot,
      "infrastructure",
      "godot",
      "lifecycle",
      "electron",
      "authority_main.mjs",
    )
  : join(
      projectRoot,
      "infrastructure",
      "godot",
      "lifecycle",
      "electron",
      "authority_main.mjs",
    );
const desktopEntry = app.isPackaged
  ? join(packagedRoot, "desktop-interface", "main.js")
  : join(projectRoot, "build", "components", "desktop-interface", "main.js");
const selectedEntry = process.argv.includes(AUTHORITY_ROLE_ARGUMENT)
  ? authorityEntry
  : desktopEntry;

await import(pathToFileURL(selectedEntry).href);
