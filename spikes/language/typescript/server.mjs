import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Fastify from "fastify";
import { z } from "zod";


const directory = path.dirname(fileURLToPath(import.meta.url));
const fixturePath = path.resolve(directory, "../../../evals/class-os-v1/fixtures/r1/canonical-r1.synthetic.json");
export const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));

const requestSchema = z
  .object({
    workspace_id: z.uuid(),
    limit: z.number().int().min(1).max(100),
  })
  .strict();

function projectItems(workspaceId) {
  if (workspaceId !== fixture.workspace_a.workspace_id) return [];
  const task = fixture.tasks[0];
  const missingRecord = fixture.records.find((record) => record.kind === "homework_missing_fact");
  const proposal = fixture.proposals[0];
  const approval = fixture.approval_requests[0];
  return [
    {
      bucket: "needs_action",
      item_id: task.task_id,
      source_ref: task.source_ref,
      summary: "合成跟进事项",
    },
    {
      bucket: "possible_miss",
      item_id: missingRecord.record_id,
      source_ref: missingRecord.student_id,
      summary: "合成待核对事实",
    },
    {
      bucket: "waiting_on_others",
      item_id: approval.approval_request_id,
      source_ref: proposal.proposal_id,
      summary: "合成等待确认事项",
    },
  ];
}

export function buildApp() {
  const app = Fastify({ logger: false });
  app.get("/health", async () => ({ status: "ok" }));
  app.post("/v1/attention/list", async (request, reply) => {
    const parsed = requestSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.code(422).send({ detail: { code: "VALIDATION_ERROR" } });
    }
    const { workspace_id: workspaceId, limit } = parsed.data;
    const knownWorkspaces = new Set([
      fixture.workspace_a.workspace_id,
      fixture.workspace_b.workspace_id,
    ]);
    if (!knownWorkspaces.has(workspaceId)) {
      return reply.code(404).send({ detail: { code: "NOT_FOUND_SAFE" } });
    }
    return {
      workspace_id: workspaceId,
      as_of: fixture.meta.clock,
      items: projectItems(workspaceId).slice(0, limit),
    };
  });
  return app;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const app = buildApp();
  const port = Number.parseInt(process.env.PORT ?? "8762", 10);
  await app.listen({ host: "127.0.0.1", port });
}
