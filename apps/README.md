# apps/

TypeScript / web apps live here, one pnpm workspace package per directory. Created on D-Day
(hackathon rule: no product code before the event).

Each app's `package.json` must define `typecheck` and `test` scripts. Once `apps/*/package.json`
exists, the quality gate and CI automatically run Biome, `pnpm -r typecheck` and `pnpm -r test`.
The app's `tsconfig.json` should extend `../../tsconfig.base.json`.
