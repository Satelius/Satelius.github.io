# P9 BUDGET-2X: preregistered exploratory trial

User authorized 2026-09-21: every new simulation retains video; double P8 decision
budget. Interpretation is 80→160, not 240. Native RoboLab success remains authoritative.

## Evidence and hypothesis

Historical calibrated P8 Luna-none/RubiksCubeTask/31001 ended at 67 decisions with
action_oscillation_replan_exhausted, below its 80-decision cap. Therefore increasing
only the total cap may leave the actual terminating constraint unchanged. Longer
budget may permit recovery, or may merely prolong incorrect movement; both remain
hypotheses. Provider randomness prevents causal claims from one historical comparison.

## Fixed sequential trials

Use the P9 measurement overlay over unchanged P8 prompts, camera, dynamics and actions.
Luna-none handles both roles, RubiksCubeTask seed31001, video policy, wall limit900s.

1. `p9-budget-total160`: max_steps160, stage24, max_replans2. Unique budget change is
   the total cap. Run once and record the actual termination reason and all limits.
2. Only if trial1 terminates at a stage/replan constraint without native success,
   `p9-budget-envelope160`: max_steps160, stage48, max_replans4, same wall900s. This
   is an explicitly combined stage/recovery-budget ablation, not a total-cap-only
   causal test. Run once, no model substitutions or added retries.

No full matrix rerun is justified by these exploratory trials. Retain both positive
and negative outcomes and videos; do not fold these episodes into the 80-step matrix.
Compare first descent/grasp, native success, executed decisions, end reason, wall time
and model calls; valid-grasp proxy caveats remain applicable.

## Execution status

- [x] Focused fake-environment happy path executed beyond80 (success at82) with cap160.
- [x] CLI defaults to video and accepts only video/full for new live runs; matrix keeps
  its80-step contract but now records video in future newly frozen versions.
- [x] Trial1 executed: native false,39 decisions,action_oscillation_replan_exhausted,
  first descent at i7, no GRASP, truth39/39. Wall128.5335s, actor p95 2.9313s. Summary
  confirms160/24/2/900. ffprobe verifies H.264512×256,5fps,8.0s including final frame.
  Total-cap expansion did not remove the earlier replan constraint in this sample.
- [x] Trial2: native false,74 decisions,env_truncated, no descent/grasp. Truth74/74,
  wall283.0488s, actor p95 3.8044s. Video H.264512×256/5fps/15s verified. This hit the
  task's40s native simulation horizon, not total160 or wall900.

## Follow-up native-time experiment (registered after trial2, before running)

New evidence: trial2 hit native40s at74 decisions. Run one separately labelled
`p9-budget-native80` with160/48/4/900 and explicit native simulation horizon80s, doubling
only the native limit relative to trial2. This is a relaxed-task-horizon ablation and
must never enter official40s baseline scores. All actions/model/prompts remain unchanged.
No further expansion or retry is planned in this budget series. Record whichever bound
ends the trial; do not imply the160 cap guarantees160 executed decisions.

- [x] Native80 follow-up:56 decisions, native false,action_oscillation_replan_exhausted;
  no descent/grasp, truth56/56, wall314.701s,actor p95 10.4471s. Video verified
  H.264512×256/5fps/11.4s. Four replans exhausted before either requested cap.

## Conclusion

All three exploratory episodes failed. Raising budgets alone did not yield grasp or
native success here; total-cap-only trial still hit a replan bound, the second hit
native simulation time, and the third again exhausted replans while moving horizontally.
The sample is not a statistical causal comparison and does not show that budget never
matters. No further budget expansion is planned; retain these as separate negative
evidence and proceed with the fixed80-step recorded baseline and source-backed E01 work.

Snapshot caveat: upstream create_env writes env_cfg.json before the wrapper's explicit
override at core/sim/robolab_task.py:299. That file still says40. The saved metadata says
requested80 and the frozen call chain assigns80 to env.cfg after construction. No separate
post-override live config snapshot was saved in this trial; do not claim otherwise.

## Existing v2 interruption

On resumption the previous benchmark parent and supplementary video waiter were absent;
only its fifth child remained (PPID1). v2 contains four terminal ledger rows at discovery.
Do not claim its stale waiting gallery represents a live queue. Allow the existing child
to finish within its old deadline, preserve its result, and start no concurrent GPU run.
The user's new video requirement supersedes the prior metrics-only continuation. Future
matrix work needs a new recorded version; v2 stays an incomplete historical run.

The old fifth child eventually wrote native false,56 steps,env_truncated and exited.
The native task's configured simulation limit is40s, independent of the900s wall bound.
Both budget trials retain this task limit; neither is an unrestricted160-action run.
