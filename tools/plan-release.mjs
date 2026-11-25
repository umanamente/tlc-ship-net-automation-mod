import { execFileSync, spawnSync } from "node:child_process";
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import semanticRelease from "semantic-release";

const bootstrap = spawnSync("git", ["merge-base", "--is-ancestor", "v0.1.0", "HEAD"], { stdio: "ignore" });
if (bootstrap.status !== 0) {
  console.log("Waiting for the initial v0.1.0 tag.");
  process.exit(0);
}

const metadata = JSON.parse(readFileSync("mod.json", "utf8"));
const result = await semanticRelease({ dryRun: true, ci: false });
if (result) {
  const { lastRelease, nextRelease } = result;
  if (lastRelease.version !== metadata.version) {
    throw new Error("The last stable tag and the current mod version differ");
  }
  mkdirSync("dist", { recursive: true });
  writeFileSync("dist/release-plan.json", JSON.stringify({
    version: nextRelease.version,
    notes: nextRelease.notes,
    base: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
  }));
}
if (process.env.GITHUB_OUTPUT) {
  appendFileSync(process.env.GITHUB_OUTPUT, `tag=${result ? result.nextRelease.gitTag : ""}\n`);
}
