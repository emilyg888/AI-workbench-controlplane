# Control Plane vs Runtime Plane

The workbench has two logical planes, enforced in code by the lint test
[`tests/test_plane_boundary.py`](../tests/test_plane_boundary.py).

## Control plane

Emits decisions and mutates registry state. Reads inputs (scored runs,
promotion rules, deployment intent) and writes outputs (bundle state
transitions, deployment history, promotion log).

Modules:

- `bundle_manager` (create / transition / snapshot)
- `deployment_state_manager` (set_active / undeploy)
- `promotion_engine` (propose / approve / reject)
- `rollback`
- `snapshot`
- `experiment_runner`
- `evaluation_engine`
- `evidence_pack`
- `doctor`
- `lineage`
- `prod_eval`

## Runtime plane

Executes the active bundle against real or test inputs. Reads the
registry; never writes registry mutations. Receives decisions; cannot
make them.

Modules:

- `runtime_resolver`
- `runtime_compare`
- `adapters/*` (model, retrieval)
- `policy/enforcer`
- `serving/invoke`
- `serving/http`

## The boundary

A runtime-plane module may:

- Read bundle records via `bundle_manager.get_bundle` / `list_bundles`.
- Read deployment state via `deployment_state_manager.get_active_full` /
  `get_active` / `list_environments`.
- Write inference-request telemetry via `db.insert_inference`.

A runtime-plane module **must not** call any of:

```
bundle_manager.{create_bundle, transition_bundle, snapshot_bundle}
deployment_state_manager.{set_active, undeploy}
promotion_engine.{propose, approve, reject}
rollback.rollback
experiment_runner.run_experiment
evaluation_engine.evaluate_run
```

Violations are caught by `test_plane_boundary::test_runtime_makes_no_control_plane_calls`.

## Why

> The runtime executes the approved active bundle, not ad-hoc configs.
> (Design §8, Principle 5.)

Keeping the planes split by contract — not just convention — means:

1. The runtime can be extracted into a separate process / container / service
   later without refactoring the imports.
2. A bug in inference code can't accidentally transition a bundle's state.
3. The control plane is the single source of mutations; every change has
   one line-numbered place in the codebase that could have produced it.
