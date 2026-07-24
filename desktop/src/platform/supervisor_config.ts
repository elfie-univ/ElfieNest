import { existsSync } from "node:fs";
import { basename, join } from "node:path";

export type SupervisorConfig = Readonly<{
  readonly dataRoot: string;
  readonly uiUrl: string;
  readonly godotUrl: string;
  readonly ollamaUrl: string;
  readonly coreHealthUrl: string;
  readonly ollamaExecutable: string;
  readonly coreExecutable: string;
  readonly coreArgs: readonly string[];
  readonly webBuildDirectory: string;
  readonly resourcesPath: string;
  readonly coreWorkingDirectory: string;
  readonly manageOllama: boolean;
}>;

type Environment = Readonly<Record<string, string | undefined>>;

function environmentValue(environment: Environment, key: string, fallback: string): string {
  const value = environment[key];
  return value === undefined || value.trim() === "" ? fallback : value;
}

function platformExecutable(platform: NodeJS.Platform, name: string): string {
  return platform === "win32" ? `${name}.exe` : name;
}

export function resolveSupervisorConfig(
  environment: Environment,
  resourcesPath: string,
  projectRoot: string,
  platform: NodeJS.Platform,
  userDataRoot: string = join(projectRoot, ".elfienest"),
): SupervisorConfig {
  const dataRoot = environmentValue(environment, "ELFIE_HOME", userDataRoot);
  const uiUrl = environmentValue(
    environment,
    "ELFIENEST_UI_URL",
    "http://127.0.0.1:8000/login",
  );
  const godotUrl = environmentValue(
    environment,
    "ELFIENEST_GODOT_URL",
    `${uiUrl.replace(/\/$/, "")}/runtime/godot/elfienest.html`,
  );
  const ollamaUrl = environmentValue(environment, "ELFIENEST_OLLAMA_URL", "http://127.0.0.1:11434");
  const coreHealthUrl = environmentValue(
    environment,
    "ELFIENEST_CORE_HEALTH_URL",
    `${uiUrl.replace(/\/$/, "")}/api/health`,
  );
  const packagedOllama = join(resourcesPath, "ollama", platform, platformExecutable(platform, "ollama"));
  const packagedCore = join(
    resourcesPath,
    "python-core",
    platformExecutable(platform, "ElfieNestCore"),
  );
  const packagedCoreAvailable = existsSync(packagedCore);
  const developmentPython = join(
    projectRoot,
    platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python3",
  );
  const coreExecutable = environmentValue(
    environment,
    "ELFIENEST_CORE_BIN",
    packagedCoreAvailable ? packagedCore : developmentPython,
  );
  const coreArgs = basename(coreExecutable).startsWith("ElfieNestCore") ? [] : ["scripts/serve.py"];
  const webBuildDirectory = environmentValue(
    environment,
    "ELFIENEST_WEB_BUILD_DIR",
    packagedCoreAvailable ? join(resourcesPath, "web") : join(projectRoot, "build", "web"),
  );
  return {
    dataRoot,
    uiUrl,
    godotUrl,
    ollamaUrl,
    coreHealthUrl,
    ollamaExecutable: environmentValue(environment, "ELFIENEST_OLLAMA_BIN", packagedOllama),
    coreExecutable,
    coreArgs,
    webBuildDirectory,
    resourcesPath,
    coreWorkingDirectory: environmentValue(
      environment,
      "ELFIENEST_CORE_CWD",
      packagedCoreAvailable ? dataRoot : projectRoot,
    ),
    manageOllama: environment["ELFIENEST_OLLAMA_EXTERNAL"] !== "1",
  };
}
