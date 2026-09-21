# Small-model roles, fast/slow control, and distillation research

Last updated: 2026-09-21

Status: **evidence-backed research draft; proposed experiments remain unexecuted**.
No online learning, learned routing, or distillation is implemented by this research
track. This document is not evidence that the five topics or small-model evaluation
are complete. The fixed API matrix and this research track proceed independently.

## Evidence rules

This note separates three labels:

- **Published evidence**: claim stated by the cited primary paper or official project.
- **Project observation**: result measured by this repository.
- **Hypothesis**: a proposed explanation or experiment, not an established result.

Primary sources consulted through their arXiv records:

- [RT-2](https://arxiv.org/abs/2307.15818), arXiv:2307.15818 — actions represented as text tokens in a VLA.
- [ACT](https://arxiv.org/abs/2304.13705), arXiv:2304.13705 — predicts action sequences to reduce compounding error and
  handle fine manipulation.
- [SayCan](https://arxiv.org/abs/2204.01691), arXiv:2204.01691 — high-level language proposals grounded by executable skill
  value functions.
- [OpenVLA](https://arxiv.org/abs/2406.09246), arXiv:2406.09246 — 7B open VLA, 970k demonstrations, LoRA/quantization study.
- [Octo](https://arxiv.org/abs/2405.12213), arXiv:2405.12213 — transformer policy trained on 800k trajectories and adapted to
  new observations/action spaces.
- [FAST](https://arxiv.org/abs/2501.09747), arXiv:2501.09747 — frequency-space sequence tokenization; reports better
  high-frequency action modeling and up to 5× training-time reduction with pi0.

These papers establish possible interfaces and training mechanisms. None proves that the
same choice improves the three Show-Harness RoboLab tasks.

## 1. Action ABI

### Published boundary

RT-2 shows that robot actions can share a token interface with language. FAST shows that
the tokenization choice materially affects continuous, high-frequency action learning.
ACT instead predicts a temporally extended continuous action sequence. These are distinct
ABIs, not interchangeable implementations of one idea.

### Local boundary

P8/P9 exposes nine controller tokens: six translations plus `GRASP`, `RELEASE`, and
`DONE` (`core/vlm/roles.py:CONTROLLER_TOKENS`). `DONE` is a stage signal, not a physical
motion or native success. Translations use the calibrated nominal 20 mm contract;
actual executed displacement remains measured separately. The hosted model receives
the ABI through prompts; this project does not train its weights, and code maps
translation decisions to IK.
The official Show-Harness 2B adapter uses a one-token action vocabulary, but has not yet
been executed locally.

**Verified local source boundary:** `plugins/action_ablation/plugin.py` already provides
`off`, `bare`, `letters`, and `letters_blind`. Only six translation names are symbolized;
gripper/completion names remain explicit. Blind mode reviews before/after images and
maintains a model-written symbol/effect table. This is in-context adaptation, not weight
training. These modes have not been validated in the P9 staged matrix. Parameterized
and continuous-action comparisons below are research proposals.

### Hypotheses and counterexamples

- Hypothesis: semantic atomic actions improve auditability and recovery because each
  decision receives fresh images.
- Counterexample: the full P9 gate produced 30 valid 20 mm motions but no descent/grasp;
  a clear ABI does not ensure correct visual grounding.
- Hypothesis: parameterized or chunked actions reduce calls during far-field approach.
- Counterexample: an incorrect open-loop chunk can amplify the left/right contradiction
  already observed in P8/P9.

### Future minimum experiment

Compare stepwise semantic tokens with the author's selective chunking after E01
audits direction semantics. Hold images, tasks, models and physical displacement fixed;
measure native success, stage progress, calls, overshoot and recovery cost.

## 2. Harness as a meta-policy

### Published boundary

SayCan is evidence that high-level semantic selection can be constrained by grounded
skills. It is not evidence for an online learned router between arbitrary cloud and local
models. Show-Harness supplies rule/plugin orchestration, not the dynamic learned router
proposed in the research brief.

### Local boundary and hypothesis

The current harness uses fixed roles: planner, actor, deterministic guards and recovery.
P9 records their sources separately. A future meta-policy could choose slow planner,
fast actor, recovery controller, or human escalation, but this cycle implements none.

Smallest future comparison: fixed routing versus a predeclared rule router. Measure native
success, intervention rate, logical calls, latency, switching frequency and false recovery.
A learned router is justified only if fixed rules leave repeatable, labelled ambiguity.

## 3. Slow-brain to fast-brain distillation

### Published boundary

OpenVLA and Octo support adaptation of generalist policies to new domains; they do not
establish that an unsuccessful hosted teacher should supervise a local policy. ACT and
FAST provide action-sequence targets/interfaces, not automatic teacher correctness.

### Project observation

The P7 hosted matrix was 0/33. P8 and the P9 full gate also failed before grasp. Therefore
their raw action traces are not reliable demonstrations. Distilling them directly would
copy oscillation and direction errors.

### Proposed offline pipeline

1. Keep only native-success trajectories or human/simulator-corrected segments.
2. Label provenance: teacher proposal, executed action, harness override, outcome.
3. Split by complete episode/layout/task, never adjacent frames.
4. Train offline; do not update the deployed actor during collection.
5. Run shadow evaluation, then the frozen simulator matrix, before promotion.

Teacher natural-language reasoning is not required. Prefer action targets plus auditable
stage/relationship labels when they add measurable closed-loop value.

## 4. Robot-local post-training/deployment

Three deployment choices must remain separate:

1. Robot collects encrypted/versioned data; training remains remote.
2. Robot trains a small adapter locally when compute and rollback permit.
3. Robot only runs an immutable local adapter produced elsewhere.

The official 2B resource gate must first measure model/download footprint, simulator and
server GPU coexistence, preprocessing, queueing, inference, execution and loop rate.
“Local” does not imply “fast”; “2B” does not imply a real-time control rate.

Release requirements: immutable dataset/model hashes, held-out episode evaluation,
shadow mode, versioned rollback, and separation of private image data from public reports.

## 5. Harness-State Distillation

Candidate target:

`(observation_t, instruction, history_t) -> (state_hat_t, action_hat_t)`

Candidate state fields are stage, target relation, visibility, alignment, gripper state,
precision mode and recovery flag.

Observability classes:

- Current-image observable: target visibility and approximate image-plane relation.
- History-dependent: oscillation, prior grasp attempt, recovery count and lost object.
- Simulator/evaluator-only: exact object centroid, native success and privileged contact
  truth. These must never become model inputs in the pure-vision comparison.
- Teacher judgement: “aligned” or “safe to descend”; this is a fallible label, not truth.

Minimum offline comparison:

1. action-only supervision;
2. joint state+action auxiliary supervision;
3. explicit predicted state followed by a separate action head.

Evaluate state accuracy/calibration, closed-loop stage gains, added latency and failure
under distribution shift. Self-reported confidence must be calibrated against held-out
outcomes; it cannot trigger autonomy merely because the model emits a high number.

## Current role/training recommendation

This is a conditional research recommendation, not an experimental conclusion:

- Follow the accepted order: official 2B simulation adapter as a direct policy;
  official 2B real adapter; corresponding unmodified base; then Astra planner
  `low/medium` with official 2B actor. These are separate added experiments and do not
  expand or replace the 11-profile API matrix. A subgoal-conditioned actor is a role
  hypothesis to examine after the direct-policy controls, not the first experiment.
- If it cannot localize reliably, test a relation/alignment auxiliary role before adding
  capacity.
- Use LoRA/SFT on corrected demonstrations first. Add stage conditioning only after the
  evaluator shows stage ambiguity. Add corrected failure segments only after labels are
  reviewed.
- Do not train on current 0-success hosted rollouts as positive action targets.

The eventual answer must state which role works under which data, latency and deployment
constraints; there is no evidence yet for a universally best fine-tuning method.

## Expanded evidence and falsifiable designs

The following designs are **hypotheses**, not extra runs authorized to bypass the
ordered feature plan. Numeric run counts and training budgets must be preregistered
when each experiment becomes eligible. The current 33 cells provide engineering
trends; adjacent frames and multiple steps are not independent episode replicates.

### Action ABI: separate semantics from temporal abstraction

**Verified source:** the local ablation plugin isolates direction names/explanations;
`plugins/action_chunk/plugin.py` accepts short ordered movement sequences. A sequence
is not necessarily a repeated direction. ACT predicts action chunks and FAST changes
continuous-action sequence tokenization; neither result establishes that renaming a
Show-Harness token improves grounding.
[ACT paper](https://arxiv.org/abs/2304.13705),
[FAST paper](https://arxiv.org/abs/2501.09747).

**Minimal future design:** first compare `off` and `letters` using the same full
physical mapping and step feedback. Treat `bare` as a separate explanation-removal
experiment. `letters_blind` additionally changes feedback/history and cannot identify
the naming effect alone. Only then compare selective chunking in E08. For future
parameterized actions, cap total displacement and measure achieved TCP motion;
continuous control needs its own controller frequency and evaluation contract.

Measure native success, valid-grasp progression, wrong-direction rate on reviewed
frames, action/description contradiction rate, executed distance per decision,
overshoot, calls per episode, and capture-to-execution latency. A naming advantage
that disappears after template correction is interface evidence, not proof of greater
policy capacity. A short token may be several tokenizer pieces: verify tokenizer IDs
before claiming single-token decoding latency.

### Meta-policy: feedback quality precedes routing complexity

**Published evidence:** SayCan combines language relevance with skill feasibility;
Inner Monologue studies feedback from success detectors, scene descriptions and human
interaction. These support grounded selection and feedback, not a demonstrated
fast/slow router for the current tasks.
[SayCan official project](https://say-can.github.io/),
[Inner Monologue paper](https://arxiv.org/abs/2207.05608).

**Counterexample/hypothesis:** repeated slow calls can consume the entire deadline
while leaving an inaccurate visual alignment estimate unchanged. Correlated planner
and actor errors can make agreement meaningless. An over-sensitive failure detector
can alternate recovery and planning without useful movement.

**Future minimum design, report only:** compare fixed routing to one frozen rule with
specified inputs, threshold, cooldown and maximum switches. Select the threshold on a
separate calibration set. Label when intervention was needed independently of the
router. Report success, slow-call and intervention rates, false interventions, missed
recoveries, consecutive routing reversals, latency percentiles, and cost per episode.
Human escalation is an intervention outcome, not autonomous success. Learning a router
would require held-out routing labels and a later scope decision; no router is built now.

### Distillation: distinguish teacher, target and update method

**Published evidence:** Policy Distillation demonstrates compressing learned policies
in Atari, including multiple teachers. It does not validate a failed robotics teacher.
DAgger explains why action-induced observation distributions undermine ordinary
independent-data assumptions and motivates expert correction on learner-visited states.
[Policy Distillation](https://arxiv.org/abs/1511.06295),
[DAgger](https://proceedings.mlr.press/v15/ross11a.html).

**Proposed data contract:** teacher source (hosted policy, demonstration, corrected
controller), supervision target (action, short structured state, or both), and optimizer
choice (LoRA/SFT) are independent fields. LoRA is a parameter-efficient update method;
it does not make a dataset a distillation dataset. Save image/history IDs, task/stage,
proposed and executed actions, override provenance, outcome and correction provenance.
Do not automatically label the executed harness override as the teacher's action.

**Counterexample:** native-success filtering can still retain unnecessary oscillations;
failure filtering can discard useful recoverable states. Success is an admission gate
for demonstrations, not proof that every action is optimal. Failed prefixes can become
correction inputs only when a qualified expert supplies labels. Teacher input available
only in simulation can create targets unidentifiable from student images/history.

**Minimum later training comparison:** action SFT; then stage-conditioned SFT; then
equal-sized corrected-trajectory SFT. Hold base, image processing, episode split,
training example count, updates and image-token budget fixed. When replacing examples
with corrections, report composition; when adding examples, add an equal-size control.
Measure native success, stage transition errors, recovery success with its denominator,
action disagreement on audited labels, train/inference cost and closed-loop latency.
Batch offline correction is inspired by distribution-shift concerns; it is not a claim
that DAgger or online distillation has been implemented.

### Local deployment: measure the entire feedback delay

**Verified official interface:** the model card specifies the adapter's training chat
template, two views, v3 prompt, and no FWD/BACK conversion for simulation. Template
mismatch can still return apparently valid actions. Adapter-only disk size is not the
base model's footprint.
[Official model card](https://huggingface.co/showlab/Show-Harness-VLMs).

**Proposed minimum measurement:** run one serving smoke, then one bounded closed-loop
episode after the resource gate. Log image capture/encoding, queue, model inference,
response parsing, action start/end and next usable image timestamps. Report end-to-end
p50/p95, decision-interval variability, useful executed actions per wall second, and
fraction of the episode spent waiting. Use service timestamps to separate network and
queueing when available; otherwise mark the decomposition unavailable. Do not subtract
unsynchronized clocks. Report cold start separately from steady state.

**Counterexample:** shared-GPU simulator rendering may delay a local 2B server enough
to lose its apparent inference advantage; reducing precision may improve speed while
changing decisions. GPU coexistence, precision, image dimensions and service batch
policy therefore belong in the manifest. Lower API latency alone does not establish
real-time control or smoother motion.

**Three deployment variants to study:** local data collection with remote training;
local adapter training; remote training with immutable local inference. For each record
resource peak, transfer volume/time, version verification, evaluation and rollback time.
Shadow action agreement is only an offline diagnostic: it cannot measure the states a
new policy would visit. Promotion requires closed-loop evaluation of the candidate.

### Harness-State Distillation: observable targets and calibrated uncertainty

**Published boundary:** Asymmetric Actor Critic trains a critic on full simulator state
while the actor uses images. This demonstrates a training/deployment information split;
it does not show that a model can reconstruct arbitrary hidden state from one frame.
[Asymmetric Actor Critic](https://arxiv.org/abs/1710.06542).
Guo et al. study probability calibration and post-hoc temperature scaling; their image
classification results do not validate an LLM's self-reported confidence in manipulation.
[Calibration paper](https://arxiv.org/abs/1706.04599).

**Proposed label contract:** for each structured field store its evidence source,
timestamp, validity mask and whether current image, history or proprioception is needed.
Occluded alignment/contact should permit `unknown`. Stage is often harness bookkeeping;
precision mode/recovery flag may be controller choices, not visible world facts. Mark
them as policy-state labels. Gripper visibility does not prove an object is held.
Any future simulator-supervised target belongs to a separately declared training arm;
privileged values never enter pure-vision inference requests.

**Counterexample:** a forced state bottleneck may drop visual detail needed for grasping;
an auxiliary label can improve state accuracy while distracting the action head.
Teacher-selected stages can encode the teacher's mistakes. Explicitly generating state
text can add latency even when action accuracy improves.

**Minimum future design, not implemented:** action-only; joint state/action with the
same visual backbone; explicit predicted state then action. Hold architecture capacity
as close as possible and report extra parameters/tokens/calls. Score per-field accuracy
and macro F1 with missing-label coverage; for probabilistic fields report Brier score
and reliability bins on a held-out calibration set. Report risk versus abstention
coverage, closed-loop native success, valid-grasp progression and added p95 latency.
An oracle-state diagnostic could quantify the bottleneck's ceiling, but is labelled
privileged and never included in the main pure-vision score.

## Role selection and completion criteria

All four roles remain candidates. Direct policy tests whole-task execution; local actor
tests execution conditional on a subgoal; relation/alignment module tests perception
with a fixed downstream controller; failure detector tests recognition and recovery
proposals with reviewed event labels. Changing both the role and downstream controller
cannot attribute a gain to the small model alone.

Follow the accepted adapter sequence above before training. A base comparison needs
the same ABI/images while explicitly logging unavoidable template differences; a
base model's parse failure and an adapter's physical failure are separate outcomes.
If the simulation adapter succeeds but real adapter fails, domain/template shift is a
candidate explanation, not proof that real data is harmful. If the direct policy fails
but a subgoal actor succeeds, test whether improvement came from extra calls, easier
instructions or planner information before crediting role specialization.

This report becomes experimentally resolved only after those role controls and the
eligible minimal training comparisons have artifact-backed results. Until then, the
recommendation is conditional: corrected action SFT for demonstrated action errors;
stage conditioning for measured phase ambiguity; relation supervision for measurable
visual errors; failure/recovery supervision for audited recovery events. Structured
state joint supervision remains design-only in this cycle. No universal best method,
local real-time rate, or distillation benefit has been measured here.
