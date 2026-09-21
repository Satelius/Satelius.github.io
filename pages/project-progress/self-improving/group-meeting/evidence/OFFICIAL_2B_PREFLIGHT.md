# Official Qwen3.5-2B: metadata and interface preflight

Date: 2026-09-21. Status: **read-only preflight; serving and GPU coexistence pending**.
This check downloaded only public JSON/template metadata into command output. No model
weights, packages, GPU workloads or provider requests were started. The main API matrix
can continue without contention from this check.

## Frozen identities and evidence

**Verified:** Hugging Face API metadata agrees with
`requirements/robolab-stack.lock.toml`:

- Base dependency: `Qwen/Qwen3.5-2B`, revision
  `15852e8c16360a2fea060d615a32b45270f8a8fc`.
- Adapter repository: `showlab/Show-Harness-VLMs`, revision
  `c1c94dfa0f5f1e8827acbc9698ba5f765f1605e5`.
- First experiment adapter: `qwen3_5_2b_sim`; later real adapter: `qwen3_5_2b`.
- Simulation weight LFS SHA256:
  `82f8cb6d177722b05a3705dbd7ce9fb558435321a114e70572a0c89378a5aa49`.
- Real weight LFS SHA256:
  `77e6a10bf5ebd9027ea4cd74ad2f1142236e57200fe1ff23318d0df33b3187e1`.
- Base weight LFS SHA256:
  `aa33250c4fc64891ddfaba3a314fd9542ea371843c387178b425fbcc5ed680b1`.

These are remote metadata checksums, not local weight verification. Adapter config
specifies `base_model_name_or_path: Qwen/Qwen3.5-2B` but `revision: null`; therefore the
base revision above is this project's explicit pin, not proof of the training-time
base revision. The later "unmodified base" control means this adapter dependency
without LoRA, not silently substituting `Qwen3.5-2B-Base`.

Sources: [base API](https://huggingface.co/api/models/Qwen/Qwen3.5-2B?blobs=true),
[adapter API](https://huggingface.co/api/models/showlab/Show-Harness-VLMs?blobs=true),
[pinned adapter config](https://huggingface.co/showlab/Show-Harness-VLMs/blob/c1c94dfa0f5f1e8827acbc9698ba5f765f1605e5/qwen3_5_2b_sim/adapter_config.json).

## Disk estimate, derived from file metadata

**Verified metadata:** base weight is 4,548,221,488 bytes. Sum of all 13 base sibling
file sizes is 4,571,274,023 bytes. Each selected 2B adapter weight is 134,610,104 bytes;
sum of its seven directory files is 154,612,786 bytes including tokenizer/template.

**Derived payload estimates:** base plus simulation adapter is 4,725,886,809 bytes;
base plus both simulation and real adapter directories is 4,880,499,595 bytes, before
cache deduplication. Do not use repository-wide `usedStorage` for a selected download.
These sums exclude dependency wheels, environments, temporary download copies, JIT
caches, logs and GPU memory. Dependency installation space remains **unknown**.

**Observed:** `df -B1 .` reported 141,417,631,744 bytes available during the running API
matrix. This is a timestamped observation, not reserved capacity. No default project
`models/huggingface` directory or standard home-cache snapshots for these two repositories
were found. Other custom caches have not been exhaustively searched; do not conclude
that the machine contains no reusable weights.

## Local service compatibility

**Verified source:** `scripts/serve_vlm.sh` targets a separate `.venv-vllm`, serves BF16,
defaults to port 8000, tensor parallel 1, model length 8192, maximum sequences 256 and
GPU utilization 0.9. With `FAMILY=qwen3_5`, it selects
`models/chat_templates/qwen3_5_nothink.jinja`; LoRA rank limit defaults to 64. It checks
adapter files before launch and rejects an occupied serving port. The defaults describe
source behavior, not a configuration already safe for simulator coexistence.

**Observed:** `.venv-vllm` is absent; `command -v vllm` found no executable. The bounded
checks of standard miniconda/anaconda environment executable locations found none.
CPU-only `importlib.metadata` inspection of `.venv-robolab` found:

- vLLM: absent; PEFT: absent.
- Transformers: 5.17.0; Torch: 2.7.0+cu128; huggingface-hub: 1.16.1.

The repository's separate serving requirements pin vLLM 0.24.0, Transformers 5.12.1,
and huggingface-hub 1.17.0. These are source pins, not installed compatibility evidence.
No Torch/CUDA/model import was used in this check. Service discovery outside those
locations and any existing local inference endpoint remain **unknown**; no endpoint
was called. Reuse discovery should precede installation. Do not modify the working
simulator environment to satisfy the separate inference requirements.

## Input/output contract

**Verified adapter config:** LoRA rank 64, alpha 128, dropout 0.05, PEFT version 0.18.1,
task type CAUSAL_LM. Target modules are `out_proj`, `in_proj_z`, `up_proj`, `k_proj`,
`in_proj_a`, `in_proj_qkv`, `o_proj`, `v_proj`, `down_proj`, `in_proj_b`, `q_proj`,
`gate_proj`. These include hybrid-model projections: successful plain base serving
does not prove successful adapter loading for every target module.

**Verified template parity:** local `git hash-object` is
`567088a3bda735237f5cb709a418ff4f6ee611ed`, identical to the API blob ID for both adapter
chat templates. The no-thinking generation prefix ends directly after the assistant
turn marker. The base template inserts an empty think block when thinking is disabled;
using that template for the adapter changes its input distribution. Rendered request
and token-ID parity still need a CPU/service smoke before live evaluation.

**Verified source interface:** `VLMClient.complete_action_token` sends agentview then
wrist images, followed by prompt text; forces no-thinking template kwargs and requests
a bare action, without guided-choice decoding. Nine allowed semantic strings are the
six `MV_*` translations plus `GRASP`, `RELEASE`, `DONE`; one semantic string does not
guarantee one tokenizer ID. The direct-policy entry point is
`scripts/run_robolab_mvtoken.py`, whose prompt-version default is `v3`. This is distinct
from the P8 custom visual-recovery JSON actor; do not silently reuse that JSON protocol
for the official adapter.

**Verified current source geometry:** `configs/robot_robolab.yaml` letterboxes both views
to 256 square; agentview crop is null, wrist crop aspect 1.3333, wrist rotation 270
degrees, flip none. The P8 overlay changes wrist pose. These source settings are not a
new validation of the direct-policy runner using the P8 calibration. Retain the audited
P8 camera and verify exact sent frames before calling the small-model comparison fair.

**Verified processor metadata:** adapter `processor_config.json` names Qwen3VLProcessor
and Qwen2VLImageProcessor; base `preprocessor_config.json` names
Qwen2VLImageProcessorFast. Both list patch size 16, temporal patch size 2, merge size 2,
mean/std 0.5 and size fields 65536/16777216. Adapter config also explicitly enables RGB,
resize, rescale by 1/255 and normalize. Equal scalar values do not prove identical
processor implementation outputs. The service's selected processor, resized dimensions
and image-token counts remain pending; do not interpret those size fields as camera
width/height without checking processor semantics.

**Published contract:** official model card says directions follow the Franka overhead
view; simulation needs no FWD/BACK conversion. AgileX conversion must not leak into the
simulation adapter. Each translation is nominally 2 cm; log measured motion rather than
assuming IK command equals displacement. The card requires v3 prompts.

Sources: [model card](https://huggingface.co/showlab/Show-Harness-VLMs),
[pinned adapter processor](https://huggingface.co/showlab/Show-Harness-VLMs/blob/c1c94dfa0f5f1e8827acbc9698ba5f765f1605e5/qwen3_5_2b_sim/processor_config.json),
[pinned base processor](https://huggingface.co/Qwen/Qwen3.5-2B/blob/15852e8c16360a2fea060d615a32b45270f8a8fc/preprocessor_config.json).

## Gate disposition and next eligible steps

- [x] Freeze repository revisions and remote weight metadata.
- [x] Estimate selected download payload from file sizes; inspect disk and local package metadata.
- [x] Verify local training-template bytes and document image/action contract.
- [ ] Discover reusable serving environments/services beyond the bounded locations checked.
- [ ] Resolve serving compatibility in a separate environment, if reuse is unavailable.
- [ ] Verify downloaded hashes and actual processor/template rendering before model evaluation.
- [ ] Measure GPU coexistence with Isaac Sim, including peak memory, queueing, image processing,
  inference, action execution and closed-loop throughput. **Not measured in this check.**
- [ ] Smoke then bounded direct-policy episode on the calibrated camera, retaining parser and
  infrastructure failures separately from task failures.
- [ ] Evaluate sim adapter on the same three tasks, then real adapter, unmodified dependency
  base, and finally Astra low/medium plus official 2B actor. Keep these outside the 11-profile matrix.

The metadata/resource preflight is useful preparation but does not pass the live serving
or resource-coexistence gate. No GPU memory number is inferred from parameter count or
download size. No downloads or installation are required to continue the API experiment.

## Check limitations

The web reader could not open HF API/raw metadata URLs; bounded `curl -fsSL --max-time 30`
requests succeeded. Some guessed local source/cache paths did not exist; the actual
image serializer was subsequently located at `core/record/images.py`. These were
read-only discovery failures, not serving failures. No model was loaded, no package
installed, no inference endpoint probed, and no GPU command run for this document.
