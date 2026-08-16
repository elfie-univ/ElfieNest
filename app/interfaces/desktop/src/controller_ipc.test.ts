import assert from "node:assert/strict";
import { createConnection } from "node:net";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  CONTROLLER_SOCKET_FILENAME,
  CONTROLLER_TOKEN_FILENAME,
  startControllerIpcServer,
} from "./controller_ipc.js";

test("Controller IPC authenticates commands and removes its endpoint", async () => {
  const home = await fs.mkdtemp(join(tmpdir(), "elfienest-controller-"));
  const server = await startControllerIpcServer(home, {
    STATUS: async () => ({ state: "owned" }),
  });
  const token = (await fs.readFile(join(home, CONTROLLER_TOKEN_FILENAME), "utf8")).trim();

  const response = await request(
    join(home, CONTROLLER_SOCKET_FILENAME),
    JSON.stringify({ protocol: 1, token, command: "STATUS", payload: {} }),
  );
  assert.deepEqual(JSON.parse(response), { ok: true, result: { state: "owned" } });

  const rejected = await request(
    join(home, CONTROLLER_SOCKET_FILENAME),
    JSON.stringify({ protocol: 1, token: "wrong", command: "STATUS", payload: {} }),
  );
  assert.deepEqual(JSON.parse(rejected), {
    ok: false,
    error: "Controller authentication failed",
  });

  await server.close();
  await assert.rejects(() => fs.access(join(home, CONTROLLER_SOCKET_FILENAME)));
  await assert.rejects(() => fs.access(join(home, CONTROLLER_TOKEN_FILENAME)));
  await fs.rm(home, { recursive: true, force: true });
});

function request(socketPath: string, frame: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const socket = createConnection(socketPath);
    let output = "";
    socket.setEncoding("utf8");
    socket.on("data", (chunk: string) => {
      output += chunk;
      if (output.includes("\n")) {
        socket.end();
        resolve(output.split("\n", 1)[0] ?? "");
      }
    });
    socket.on("error", reject);
    socket.on("connect", () => socket.write(`${frame}\n`));
  });
}
