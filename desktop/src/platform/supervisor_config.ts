import { existsSync } from "node:fs";
import { basename, join } from "node:path";

export type SupervisorConfig = Readonly<{
  readonly dataRoot: string;
  readonly uiUrl: string;
  readonly godotUrl: string;
  readonly ollamaUrl: string;
  readonly coreHealthUrl: string;
  readonly coreExecutable: string;
  readonly coreArgs: readonly string[];
  readonly webBuildDirectory: string;
  readonly godotWebDirectory: string;
  readonly resourcesPath: string;
  readonly coreWorkingDirectory: string;
  readonly runtimeMode: "development" | "release";
  readonly ollamaOptional: boolean;
}>;

type Environment = Readonly<Record<string, string | undefined>>;

function environmentValue(environment: Environment, key: string, fallback: string): string {
  const value = environment[key];
  return value === undefined || value.trim() === "" ? fallback : value;
}

function optionalPortArgument(
  environment: Environment,
  environmentKey: string,
  argument: "--port" | "--ws-port" | "--godot-ws-port",
): readonly string[] {
  const value = environment[environmentKey]?.trim();
  if (value === undefined || value === "") {
    return [];
  }
  if (!/^[1-9][0-9]{0,4}$/.test(value) || Number(value) > 65535) {
    throw new Error(`无效端口 ${environmentKey}=${value}`);
  }
  return [argument, value];
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
  const coreBaseArgs = basename(coreExecutable).startsWith("ElfieNestCore")
    ? ["--lan"]
    : ["scripts/serve.py", "--lan"];
  const coreArgs = [
    ...coreBaseArgs,
    ...optionalPortArgument(environment, "ELFIENEST_CORE_PORT", "--port"),
    ...optionalPortArgument(environment, "ELFIENEST_WS_PORT", "--ws-port"),
    ...optionalPortArgument(environment, "ELFIENEST_GODOT_WS_PORT", "--godot-ws-port"),
  ];
  const webBuildDirectory = environmentValue(
    environment,
    "ELFIENEST_WEB_BUILD_DIR",
    packagedCoreAvailable ? join(resourcesPath, "web") : join(projectRoot, "build", "web"),
  );
  const runtimeMode = packagedCoreAvailable ? "release" : "development";
  const godotWebDirectory = environmentValue(
    environment,
    "ELFIENEST_GODOT_WEB_DIR",
    packagedCoreAvailable
      ? join(resourcesPath, "godot-web")
      : join(projectRoot, "build", "components", "godot-web"),
  );
  return {
    dataRoot,
    uiUrl,
    godotUrl,
    ollamaUrl,
    coreHealthUrl,
    coreExecutable,
    coreArgs,
    webBuildDirectory,
    godotWebDirectory,
    resourcesPath,
    coreWorkingDirectory: environmentValue(
      environment,
      "ELFIENEST_CORE_CWD",
      packagedCoreAvailable ? dataRoot : projectRoot,
    ),
    runtimeMode,
    ollamaOptional: environment["ELFIENEST_OLLAMA_REQUIRED"] !== "1",
  };
}
