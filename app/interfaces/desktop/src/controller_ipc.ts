import { randomBytes, timingSafeEqual } from "node:crypto";
import { promises as fs } from "node:fs";
import { createServer, type Server, type Socket } from "node:net";
import { join } from "node:path";

export const CONTROLLER_IPC_PROTOCOL = 1;
export const CONTROLLER_NAMESPACE = "elfienest.desktop-ui";
export const CONTROLLER_TOKEN_FILENAME = "controller.token";
export const CONTROLLER_SOCKET_FILENAME = "controller.sock";
const CONTROLLER_ENDPOINT_FILENAME = "controller.endpoint.json";
const MAX_FRAME_BYTES = 64 * 1024;

export type ControllerIpcPayload = Readonly<Record<string, unknown>>;
export type ControllerIpcHandler = (
  payload: ControllerIpcPayload,
) => Promise<ControllerIpcPayload>;

export type ControllerIpcServer = Readonly<{
  readonly tokenPath: string;
  readonly close: () => Promise<void>;
}>;

export function controllerHomeForAppData(appDataPath: string): string {
  return join(appDataPath, "ElfieNest", CONTROLLER_NAMESPACE);
}

export async function startControllerIpcServer(
  home: string,
  handlers: Readonly<Record<string, ControllerIpcHandler>>,
): Promise<ControllerIpcServer> {
  await fs.mkdir(home, { recursive: true, mode: 0o700 });
  const tokenPath = join(home, CONTROLLER_TOKEN_FILENAME);
  const token = randomBytes(32).toString("base64url");
  await fs.writeFile(tokenPath, `${token}\n`, { encoding: "utf8", mode: 0o600 });
  const server = createServer((socket) => {
    void handleConnection(socket, token, handlers);
  });
  const socketPath = join(home, CONTROLLER_SOCKET_FILENAME);
  const endpointPath = join(home, CONTROLLER_ENDPOINT_FILENAME);
  const useTcpFallback = process.platform === "win32";

  if (useTcpFallback) {
    await fs.rm(endpointPath, { force: true });
    await listen(server, 0, "127.0.0.1");
    const address = server.address();
    if (address === null || typeof address === "string") {
      await closeServer(server);
      throw new Error("Controller IPC did not publish a TCP endpoint");
    }
    await fs.writeFile(
      endpointPath,
      `${JSON.stringify({ transport: "tcp", host: "127.0.0.1", port: address.port })}\n`,
      { encoding: "utf8", mode: 0o600 },
    );
  } else {
    await fs.rm(socketPath, { force: true });
    await listen(server, socketPath);
  }

  return {
    tokenPath,
    close: async () => {
      await closeServer(server);
      await fs.rm(socketPath, { force: true });
      await fs.rm(endpointPath, { force: true });
      await fs.rm(tokenPath, { force: true });
    },
  };
}

async function handleConnection(
  socket: Socket,
  token: string,
  handlers: Readonly<Record<string, ControllerIpcHandler>>,
): Promise<void> {
  socket.setEncoding("utf8");
  let frame = "";
  try {
    for await (const chunk of socket) {
      frame += String(chunk);
      if (Buffer.byteLength(frame, "utf8") > MAX_FRAME_BYTES) {
        throw new Error("Controller IPC frame is too large");
      }
      const newline = frame.indexOf("\n");
      if (newline < 0) continue;
      const line = frame.slice(0, newline);
      await handleFrame(socket, line, token, handlers);
      return;
    }
  } catch (error: unknown) {
    await writeResponse(socket, {
      ok: false,
      error: error instanceof Error ? error.message : "Controller IPC failed",
    });
  } finally {
    socket.end();
  }
}

async function handleFrame(
  socket: Socket,
  line: string,
  token: string,
  handlers: Readonly<Record<string, ControllerIpcHandler>>,
): Promise<void> {
  let request: unknown;
  try {
    request = JSON.parse(line);
  } catch {
    await writeResponse(socket, { ok: false, error: "Controller request is not JSON" });
    return;
  }
  if (typeof request !== "object" || request === null || Array.isArray(request)) {
    await writeResponse(socket, { ok: false, error: "Controller request must be an object" });
    return;
  }
  const protocol = Reflect.get(request, "protocol");
  const receivedToken = Reflect.get(request, "token");
  const command = Reflect.get(request, "command");
  const payload = Reflect.get(request, "payload");
  if (
    protocol !== CONTROLLER_IPC_PROTOCOL
    || typeof receivedToken !== "string"
    || !tokensEqual(receivedToken, token)
    || typeof command !== "string"
    || (payload !== undefined
      && (typeof payload !== "object" || payload === null || Array.isArray(payload)))
  ) {
    await writeResponse(socket, { ok: false, error: "Controller authentication failed" });
    return;
  }
  const handler = handlers[command];
  if (handler === undefined) {
    await writeResponse(socket, { ok: false, error: "Controller command is unsupported" });
    return;
  }
  try {
    const result = await handler((payload ?? {}) as ControllerIpcPayload);
    await writeResponse(socket, { ok: true, result });
  } catch (error: unknown) {
    await writeResponse(socket, {
      ok: false,
      error: error instanceof Error ? error.message : "Controller command failed",
    });
  }
}

function tokensEqual(received: string, expected: string): boolean {
  const receivedBytes = Buffer.from(received);
  const expectedBytes = Buffer.from(expected);
  return receivedBytes.length === expectedBytes.length
    && timingSafeEqual(receivedBytes, expectedBytes);
}

async function writeResponse(socket: Socket, response: ControllerIpcPayload): Promise<void> {
  if (!socket.destroyed) socket.write(`${JSON.stringify(response)}\n`);
}

function listen(server: Server, pathOrPort: string | number, host?: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const onError = (error: Error): void => {
      server.off("listening", onListening);
      reject(error);
    };
    const onListening = (): void => {
      server.off("error", onError);
      resolve();
    };
    server.once("error", onError);
    server.once("listening", onListening);
    if (typeof pathOrPort === "number") {
      if (host === undefined) server.listen(pathOrPort);
      else server.listen(pathOrPort, host);
    } else {
      server.listen(pathOrPort);
    }
  });
}

function closeServer(server: Server): Promise<void> {
  if (!server.listening) return Promise.resolve();
  return new Promise((resolve) => server.close(() => resolve()));
}
