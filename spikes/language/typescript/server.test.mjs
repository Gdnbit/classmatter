import assert from "node:assert/strict";
import test from "node:test";

import { buildApp, fixture } from "./server.mjs";


test("attention contract and workspace projection", async () => {
  const app = buildApp();
  const workspaceId = fixture.workspace_a.workspace_id;
  const response = await app.inject({
    method: "POST",
    url: "/v1/attention/list",
    payload: { workspace_id: workspaceId, limit: 20 },
  });
  assert.equal(response.statusCode, 200);
  const body = response.json();
  assert.equal(body.workspace_id, workspaceId);
  assert.equal(body.as_of, fixture.meta.clock);
  assert.deepEqual(body.items.map((item) => item.bucket), [
    "needs_action",
    "possible_miss",
    "waiting_on_others",
  ]);
  for (const item of body.items) {
    assert.deepEqual(Object.keys(item).sort(), ["bucket", "item_id", "source_ref", "summary"]);
  }
  await app.close();
});

test("unknown workspace is not found safe", async () => {
  const app = buildApp();
  const response = await app.inject({
    method: "POST",
    url: "/v1/attention/list",
    payload: { workspace_id: "00000000-0000-0000-0000-000000000000", limit: 20 },
  });
  assert.equal(response.statusCode, 404);
  assert.deepEqual(response.json(), { detail: { code: "NOT_FOUND_SAFE" } });
  await app.close();
});

test("unknown request field is rejected", async () => {
  const app = buildApp();
  const response = await app.inject({
    method: "POST",
    url: "/v1/attention/list",
    payload: { workspace_id: fixture.workspace_a.workspace_id, limit: 20, write: true },
  });
  assert.equal(response.statusCode, 422);
  await app.close();
});
