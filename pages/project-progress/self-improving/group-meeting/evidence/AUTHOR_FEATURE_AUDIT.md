# P9 phase A — author feature difference audit

Last updated: 2026-09-21

## Evidence set

This ledger separates author claims, public implementation, and the local P8 RoboLab
execution path.

- Paper: *Show-Harness: Just a VLM Agent Can Play Robots*, arXiv:2609.10522v1,
  sections 3.3, 5.1, 5.4.3, and appendix 7.4.
- Official repository: `https://github.com/showlab/Show-Harness.git`; local
  `origin/main` is `137d5718c3b7af0150764d8f9beeb252c9f2794a`.
- Official model card:
  `https://huggingface.co/showlab/Show-Harness-VLMs`.
- Local P8 implementation: completed commit `8f073a7`; the full live episode was
  generated at `c877d35`, before the final fail-closed source hardening.

The research ideas Action ABI, harness-as-meta-policy, slow→fast distillation, local
post-training, and Harness-State Distillation are hypotheses for P9 reporting. The paper
does not establish them as implemented Show-Harness plugins.

## Paper defaults and evaluation boundary

Verified from paper section 5.1:

- zero-shot default model is Gemini-3.1 Pro with medium thinking effort;
- basic real-robot experiments use 10 randomized trials per task and a 50-step cap;
- Adaptive Step uses 2 cm when the target is visible in the wrist view and 4 cm otherwise;
- Action History retains five recent actions;
- all section 3.3 plugins are default-on except Situated Planning and Visual Prompt,
  which are enabled only for targeted tasks.

The P9 Astra/Luna 11×3 matrix is therefore a reproduction/transfer study, not a claim that
it duplicates the paper's model, trial count, hardware, or default episode budget.

## Feature ledger

### 1. Multi-View Guidance

**Author evidence**

- Paper section 3.3: global view provides scene context; wrist view provides fine-grained
  alignment/manipulation evidence.
- Appendix 7.4.1: grasp stage + target in wrist → wrist is primary; otherwise AgentView is
  primary. The controller selects the largest visible deviation.
- Fig. 9: default 96% versus 58% with global-only input on the five real Plate tasks.

**Official code**

- Paper/code mapping: `plugins/README.md`; prompt scaffolding plus
  `core/prompting/wrist_marker.py`.
- `ControllerAgent` renders/parses the shared wrist marker when variable step or chunking
  needs it (`core/vlm/roles.py:345,427-432,590-596`).

**Local P8 status: partial/custom**

- Camera geometry is corrected and both images reach the actor.
- P8 replaces the standard `ControllerAgent` with
  `VisualRecoveryActor` (`scripts/run_robolab_staged.py:289-291`).
- Its prompt gives calibrated wrist direction rules and asks for
  `wrist_target_visible`, but does not use the official `WRIST: YES/NO` marker,
  official A/B primary-guide block, or shared marker consumers.
- The 67-decision run kept both views visible but still logged description/action
  contradictions.

**Smallest validation**

Offline image/action-direction contract plus one live bounded episode measuring assessment
versus action consistency, without changing protocol, history, step size, or recovery.

### 2. Zero-shot actor output protocol

**Author evidence**

- Appendix 7.4.1 default contract is structured JSON:
  `{"decision":"ONE_ACTION","reasoning":"one visual sentence"}`.
- Reasoning-oriented backbones use the same action alphabet but recover the final unit
  from their response.
- The instruction is “Think one visual sentence, then commit”; `reasoning_cot=false`
  does not prove the provider performed no internal reasoning.

**Official code**

- `core/vlm/roles.py:345+` implements `ControllerAgent`, guided decision JSON,
  malformed-JSON recovery, strict-token retry, and a separate CoT path.

**Local P8 status: deliberate divergence**

- `VisualRecoveryActor` requires
  `decision, observation, target_visible, wrist_target_visible, aligned, contact_risk`
  (`core/sim/visual_recovery.py:11+`).
- P8 Luna-none raises max output tokens from the OpenRouter profile's 256 to 512.
- The visible `observation` is assessment evidence, not hidden reasoning.
- Request telemetry records usage and parse/transport status, but the current P8 report
  does not yet expose truncation/finish reason as a first-class metric.

**Smallest validation**

Hold effort/model/prompts/images fixed; compare P8 assessment JSON with the official
decision+one-sentence protocol. Measure valid response, truncation, parse/recovery,
direction consistency, stage progress, and latency.

### 3. Proprioception

**Author evidence**

- Paper section 3.3: gripper height, step displacement, phase-aware hints, contact, and
  gripper state.
- Appendix fragments include table gap, fine/coarse step sizes, descend-first/holding
  hints, last-descent measured versus commanded, and gripper width.
- Fig. 9: default 96% versus 68% without proprioception.

**Official code**

- `plugins/proprioception/plugin.py:41+` implements these prompt fragments.
- Full real runner wires the plugin through `core/launch.py:937+` and supplies real
  state in `core/runners/real.py`.

**Local P8 status: missing**

- RoboLab config declares only `auto_release` in its plugin block.
- P8 staged actor call explicitly passes `proprio=None`
  (`core/sim/staged_robolab_runner.py:880`).
- P8 visual assessment and TCP safety guard are not author-style proprioceptive context.

**Smallest validation**

Evaluator/model boundary test, prompt snapshot, fake-env contact/descent case, then one
image+language+proprioception live episode.

### 4. Subtask Planning and completion

**Author evidence**

- Ordered visual stages with image-checkable completion; the model owns transitions.
- Appendix planner merges approach/align/lower/close into GRASP, separates LIFT, and adds
  RETREAT after RELEASE.
- Fig. 9: default 96% versus 60% without planning.

**Official code**

- `plugins/subgoal/agent.py:35,77+` and `plugins/subgoal/plugin.py:18+`.
- Full runner can disable planning and use a whole-task stage; public Franka default
  enables it.

**Local P8 status: implemented with local stage policy**

- Staged runner always constructs the planner, validates its route, and advances on model
  `DONE`; only native RoboLab success ends the episode successfully.
- P8 uses 24 actor decisions per stage and two replans, resets replacement plans to index
  zero, and can terminate on oscillation/replan exhaustion.
- These local budget/recovery choices are not the author's completion mechanism and
  changed relative to P7; their effect is not isolated.

**Smallest validation**

Add explicit stage-entry/exit/DONE/completion/budget records before changing behavior;
then compare author-aligned completion independently of any budget change.

### 5. Situated Planning

**Author evidence**

- Defers unresolved branches until evidence becomes visible.
- Default-off for regular tasks; targeted hidden-object task improves 35%→85% in Fig. 9.

**Official code**

- `plugins/deepplan/plugin.py:60+` and its resolver agent/prompt.

**Local P8 status: absent, appropriate for main tasks**

- P8 does not wire DeepPlan; staged planning rejects `REASON` stages.
- None of the three fixed cube/bowl tasks has yet been shown to require an unresolved
  branch.

**Decision**

Keep out of the main matrix. Only test on a separately frozen conditional task if phase A
task analysis demonstrates need.

### 6. Action Chunking / selective chunking

**Author evidence**

- Far target: one model call emits a short sequence of semantic moves; near interaction:
  return to stepwise feedback.
- Fig. 9/text: no chunking retains 96% but uses more calls; always-on drops to 74%;
  selective chunking is preferred.

**Official code**

- `ActionChunkPlugin` parses up to `step_num` arbitrary ordered `MV_*` moves, not a
  repeated single action (`plugins/action_chunk/plugin.py:35+`).
- `core/runners/real.py:403-421` executes the first planned move then queues the
  remaining distinct moves open-loop.
- Franka default enables it with `step_num=3`.

**Local P8 status: missing**

- Staged runner does not build or execute `ActionChunkPlugin`.
- P8 custom actor has no `WRIST:` marker or `PLAN:` field.

**Smallest validation**

Parser/queue unit test, bounded far-target smoke, then stepwise versus selective chunking.
Always-on chunking is a bounded ablation only.

### 7. Adaptive Step

**Author evidence**

- Paper default: 4 cm when target is not visible in wrist; 2 cm when visible.
- Fine-only is slower/timeout-prone; coarse-only overshoots; adaptive reaches 96% in the
  paper's real-robot ablation.

**Official code**

- `VariableStepPlugin` selects coarse for MV_UP, high table gap, or
  `target_in_wrist=false` (`plugins/variable_step/plugin.py:30+`).
- Franka config enables 2/4 cm and the full controller forwards the wrist marker.

**Local P8 status: missing**

- RoboLab controller uses one calibrated physical ~20 mm move for all translations.
- Neither variable-step prompt nor per-token step override is wired into staged execution.

**Smallest validation**

Provider-free calibration for fine/coarse physical travel, fake-env selection test, then
one live episode measuring approach speed, overshoot, and grasp-stage progress.

### 8. Visual Prompt

**Author evidence**

- Dedicated pointing call for an ambiguous interaction region.
- Default-off on regular tasks; targeted handle task improves 40%→85%.

**Official code**

- `plugins/affordance/plugin.py:74+` plus pointing/verification agents.

**Local P8 status: absent, appropriate by default**

- The fixed cube/bowl tasks have not been shown to require a marked handle/contact point.
- P8 assessment flags are not a visual prompt/dot.

**Decision**

Exclude from main results unless a separate need test demonstrates textual affordance is
insufficient.

### 9. Action History

**Author evidence**

- Five most recent actions, newest first.
- Appendix official rule prohibits the immediate opposite move and tells alternating
  histories to prioritize vertical escape.
- Fig. 9: removing history lowers success to 76% and raises average steps from 30 to 39.

**Official code**

- `MemTextPlugin` and `plugins/mem_text/mem_text.txt`; Franka default length 5.

**Local P8 status: implemented but intentionally diverged**

- Staged runner retains up to 8 recent actions
  (`core/sim/staged_robolab_runner.py:35,647`).
- `VisualRecoveryActor` bypasses the standard `MemTextPlugin` rendering and receives a
  JSON field containing that runner history.
- Local P8 changed the official rule after an observed failure: opposite moves are allowed
  for visible overshoot correction; alternation now triggers re-observation, never descent.

**Smallest validation**

No blind “restore paper text.” First quantify official-5 versus P8-8/current-rule on
contradiction, reversal, no-progress, descent, and stage progress. The old official text
already caused a local unsafe descent and remains negative evidence.

### 10. Failure Recovery

**Author evidence**

- Detect empty/lost grasp, reopen/reset gripper, and roll back to the relevant GRASP
  subtask.
- Fig. 9: removing recovery lowers success from 96% to 72%.

**Official code**

- `RecoveryPlugin` classifies measured gripper width, waits for unsettled close, rejects
  unverified GRASP completion, detects lost grasp, and returns a rollback index
  (`plugins/recovery/plugin.py:57+`).
- Full runner consumes it before decisions and after steps.

**Local P8 status: partial/different**

- `auto_release` can reopen a closed-empty gripper and trigger a generic replan.
- P8 visual guard can hold unsafe DOWN/GRASP and perform an upward harness-safety retreat
  on target loss/contact/tracking error.
- Staged runner does not wire `RecoveryPlugin`, verify holding width at GRASP DONE, or
  roll back to the nearest GRASP stage.
- The P8 live episode never issued GRASP, so neither author grasp recovery nor the new
  guard's contact/loss path was exercised live.

**Smallest validation**

Fake-env empty/unsettled/holding/lost cases with explicit stage rollback, then a live
episode only after the evaluator can distinguish close command from valid grasp.

## Complete default-harness gap

The official real Franka config enables Subtask Planning, Proprioception, Recovery,
Adaptive Step, Action Chunking, and Action History; Situated Planning and Visual Prompt
are default-off.

P8 staged RoboLab currently has:

- calibrated/custom multi-view actor;
- subtask planner;
- custom recent-action context;
- `auto_release`;
- P8 visual safety guard.

It lacks the author-default Proprioception, Action Chunking, Adaptive Step, and full
Failure Recovery integrations. Therefore P8 is not an implementation of the paper's
default harness, even though the repository contains those plugins.

## Paper versus public default/config inconsistencies

- Paper default zero-shot model is Gemini-3.1 Pro medium; P9 evaluates Astra/Luna.
- Paper basic real tasks use 50-step episodes/10 randomized trials; P9 fixes 80 decisions
  and one authored seed per task for paired engineering comparison.
- Paper says all plugins except Situated/Visual Prompt default on. Official Franka matches;
  official Piper disables Action Chunking and uses history length 3, showing embodiment
  public defaults are not identical.
- RoboLab public config is for the planner-free fine-tuned simulation adapter and declares
  only `auto_release`; the locally added staged zero-shot path is not the paper's
  released RoboLab default.
- Paper prose and extracted Fig. 9 layout are ambiguous about Adaptive Step average-step
  placement; only the qualitative fine/adaptive/coarse conclusion and 96% adaptive success
  are used here until the figure is manually rechecked.

## Fine-tuned small-model facts for the later appendix

Verified from paper section 3.4/5.1/7.4.2 and the official model card:

- default FT backbone is Qwen3.5-2B;
- fine-tuned mode is planner-free by default and outputs exactly one of nine action tokens;
- the released `qwen3_5_2b_sim` adapter covers both RoboLab and ManiSkill;
- adapter training: rank-64 LoRA, alpha 128, dropout 0.05, language linear layers, frozen
  vision tower/projector, 30 sim epochs;
- official sim corpus has 13,753 samples: 7,813 RoboLab + 5,940 ManiSkill;
- all semantic translations are specified as 2 cm;
- the released training chat template must be used; the base Qwen template silently
  differs even with thinking disabled;
- simulation uses the Franka/exocentric direction convention with no FWD/BACK swap.

These facts justify the later 2B resource gate and interface checks; no model download or
success claim is made in phase A.
