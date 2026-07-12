/** Mints a dev dashboard session against the compose stack: execs into the
 *  api container (dev JWT secret) and writes {org, token, projectId} to
 *  e2e/.auth/session.json (gitignored). Google login is the only real auth
 *  path — this is the same shortcut the manual dev workflow uses. */

import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const composeFile = join(here, "..", "..", "deploy", "docker-compose.yml");

const MINT_SCRIPT = `
import asyncio, json
from sqlalchemy import select
from oriflux.config import get_settings
from oriflux.db import create_engine, create_session_factory
from oriflux.db.models import Membership, Project, User
from oriflux.security.tokens import create_access_token

async def main():
    s = get_settings()
    engine = create_engine(s)
    factory = create_session_factory(engine)
    async with factory() as session:
        user = (await session.execute(select(User).order_by(User.created_at))).scalars().first()
        memb = (await session.execute(select(Membership).where(Membership.user_id == user.id))).scalars().first()
        project = (
            await session.execute(select(Project).where(Project.org_id == memb.org_id).order_by(Project.slug))
        ).scalars().first()
        print(json.dumps({
            "org": str(memb.org_id),
            "projectId": str(project.id) if project else None,
            "token": create_access_token(user.id, s),
        }))
    await engine.dispose()

asyncio.run(main())
`;

export default async function globalSetup(): Promise<void> {
  const web = process.env.ORIFLUX_E2E_WEB_URL ?? "http://localhost:8103";
  try {
    const health = await fetch(`${web}/healthz`);
    if (!health.ok) throw new Error(String(health.status));
  } catch {
    // stack down → every spec self-skips on the missing session file
    return;
  }
  const out = execFileSync(
    "docker",
    ["compose", "-f", composeFile, "exec", "-T", "api", "python", "-c", MINT_SCRIPT],
    { encoding: "utf-8" },
  );
  mkdirSync(join(here, ".auth"), { recursive: true });
  writeFileSync(join(here, ".auth", "session.json"), out.trim());
}
