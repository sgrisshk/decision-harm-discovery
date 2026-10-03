# TASK-112 Step 5 -- how the frozen baseline engine was obtained without touching the working tree

**Method (no `git stash`, no in-place revert/reapply of `engine.py`, no risk to this shared-
worktree checkout):**

1. Copied the entire `packages/analytics/src` tree (as of this task's branch) to a scratch
   directory outside the repo:
   `<scratch>`.
2. Overwrote only `discovery/engine.py` in that copy with the exact pre-TASK-112 content, obtained
   via `git show be7e829:packages/analytics/src/policy_analytics/discovery/engine.py` (`be7e829` is
   this task's own Step 1 commit -- the pre-registration, committed before any code change, so it
   is the last commit on this branch with the original, frozen engine).
3. Verified the copy's `engine.py` sha256 equals `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`
   (`discovery-engine-v0.6.2`, matching `TASK-107`'s freeze manifest and every prior task's
   verification) -- confirmed, see Step 2's commit message and the command transcript.
4. `docs/benchmark/task-112-evidence/step5_paired_eval.py` imports `policy_analytics.*` fresh for
   each run, pointing `sys.path` at either this scratch copy ("baseline") or the real repo checkout
   ("modified") -- never mixing the two in one process, and reloading every `policy_analytics`
   module from `sys.modules` between variants so no stale bytecode crosses over. Each run also
   independently re-verifies `DISCOVERY_METHOD_VERSION` and (for baseline) the engine's sha256
   before using it, exactly like `TASK-109`'s `verify_frozen_state()`.

This repo's own actual working tree (`packages/analytics/src/policy_analytics/discovery/engine.py`)
is the Step-2-modified file throughout Step 5/6 -- it is never reverted, stashed, or temporarily
swapped. The "baseline" engine only ever exists in the scratch copy.
