import { strict as assert } from "node:assert";
import test from "node:test";

import { parseHelperResponse } from "./mobile_network_access.js";

test("parses an available SSID from the native helper response", () => {
  assert.deepEqual(
    parseHelperResponse('{"status":"available","network_name":" Dd House_guest "}'),
    { status: "available", network_name: "Dd House_guest" },
  );
});

test("preserves a denied Location Services result without blocking QR access", () => {
  assert.deepEqual(
    parseHelperResponse('{"status":"permission_denied","network_name":null}'),
    { status: "permission_denied", network_name: null },
  );
});

test("maps malformed helper output to a safe unavailable result", () => {
  assert.deepEqual(
    parseHelperResponse("not-json"),
    { status: "helper_unavailable", network_name: null },
  );
});
