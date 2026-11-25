import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { analyzeCommits } from "@semantic-release/commit-analyzer";
import { generateNotes } from "@semantic-release/release-notes-generator";

const config = JSON.parse(readFileSync(new URL("../.releaserc.json", import.meta.url)));
const options = Object.fromEntries(config.plugins);
const cwd = process.cwd();
const logger = { log() {} };
const types = [
  ["fix(winch): resume after recharge", "patch"],
  ["perf: reduce catch inventory queries", "patch"],
  ["revert: restore the previous haul threshold", "patch"],
  ["revert!: retire the old save format", "major"],
  ["feat(display): add a cargo readout", "minor"],
  ["feat!: replace the saved device state", "major"],
  ["refactor: update storage\n\nBREAKING CHANGE: existing devices need migration", "major"],
  ["docs: improve installation steps", null],
  ["chore(release): 0.1.0", null],
  ["test: add net fixtures", null],
  ["ci: update test runner", null],
  ["refactor: rename a helper", null],
];

for (const [message, expected] of types) {
  test(message.split("\n")[0], async () => {
    const release = await analyzeCommits(options["@semantic-release/commit-analyzer"], {
      cwd, logger, commits: [{ hash: "1234567", message }],
    });
    assert.equal(release, expected);
  });
}

test("release notes cover user-visible features", async () => {
  const notes = await generateNotes(options["@semantic-release/release-notes-generator"], {
    cwd, logger,
    options: { repositoryUrl: "https://github.com/example/tlc-ship-net-automation-mod" },
    commits: [{ hash: "12345678901234567890", message: "feat: add a cargo readout" }],
    lastRelease: { gitTag: "v0.1.0", version: "0.1.0" },
    nextRelease: { gitTag: "v0.2.0", version: "0.2.0" },
  });
  assert.match(notes, /add a cargo readout/);
});
