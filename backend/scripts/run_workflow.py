"""Minimal BioAPEX workflow driver.

Walks a single workflow spec end-to-end and dispatches each step to the
appropriate executor surface:

  - executor_type='python'         -> import module, call function(inputs, context)
  - executor_type='external_engine' (engine_name='superbio')
                                   -> workflows.engines.superbio.adapter.dispatch
  - executor_type='external_engine' (other engines) -> not yet implemented

This is intentionally a thin DAG runner — enough to validate the alphafold2
workflow today without waiting for the full BioAPEX runtime. It does NOT
enforce qc_gates or compliance_hooks; those should be added when BioAPEX
ships its production workflow runtime.

Usage:
    python backend/scripts/run_workflow.py workflows/alphafold2.yaml \
        --input sequence_set=path/to/seqs.json \
        --param model_preset=monomer \
        --dry-run-engine
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]

    load_dotenv(REPO_ROOT / "backend" / ".env")
except ImportError:
    pass

from workflow_specs import load_workflow_spec  # noqa: E402

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


@dataclass
class StepContext:
    """Minimal `context` object passed to Python runners."""

    base_dir: str
    run_dir: str
    workflow_id: str
    run_id: str

    def relative_path(self, path_like: Any) -> str:
        p = Path(str(path_like))
        if p.is_absolute():
            try:
                return str(p.relative_to(Path(self.base_dir).resolve()))
            except ValueError:
                return str(p)
        return str(p)


def _materialize_run_dir(spec, base_dir: Path) -> tuple[Path, str]:
    template = spec.runtime.artifact_root_template if spec.runtime else None
    template = template or "artifacts/{workflow_id}/{date}/{run_id}"
    run_id = uuid.uuid4().hex[:12]
    run_dir = base_dir / template.format(
        workflow_id=spec.workflow_id,
        date=datetime.now(timezone.utc).strftime("%Y%m%d"),
        run_id=run_id,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir, run_id


def _resolve_step_inputs(step, workflow_inputs, step_outputs):
    resolved: dict[str, Any] = {}
    for input_def in step.inputs:
        src = input_def.source
        if src.source_type == "workflow_input":
            if src.input_name not in workflow_inputs:
                raise ValueError(
                    f"step '{step.id}' input '{input_def.name}' refers to missing "
                    f"workflow input '{src.input_name}'"
                )
            resolved[input_def.name] = workflow_inputs[src.input_name]
        elif src.source_type == "step_output":
            outs = step_outputs.get(src.step_id, {})
            if src.output_name not in outs:
                raise ValueError(
                    f"step '{step.id}' input '{input_def.name}' refers to "
                    f"missing output '{src.output_name}' on step '{src.step_id}'"
                )
            resolved[input_def.name] = outs[src.output_name]
        else:
            raise ValueError(f"unsupported source_type: {src.source_type}")
    return resolved


def _substitute_template(template: str, scope: dict[str, Any]) -> Any:
    """Substitute {placeholders} from `scope` into a parameter_bindings template.

    If the template is exactly one placeholder and the scope value is non-string
    (list, dict), return that raw value. Otherwise interpolate as text.
    """
    match = PLACEHOLDER_RE.fullmatch(template)
    if match:
        key = match.group(1)
        return scope.get(key, template)

    def _repl(m: re.Match[str]) -> str:
        key = m.group(1)
        val = scope.get(key, m.group(0))
        return val if isinstance(val, str) else json.dumps(val)

    return PLACEHOLDER_RE.sub(_repl, template)


def _execute_python_step(step, inputs, context):
    module_name = step.executor.module
    function_name = step.executor.function
    module = import_module(module_name)
    fn = getattr(module, function_name)
    return fn(inputs, context)


def _execute_external_engine_step(step, inputs, workflow_inputs, step_outputs, dry_run_engine):
    engine_name = step.executor.engine_name
    if engine_name != "superbio":
        raise NotImplementedError(
            f"external_engine dispatch for engine_name={engine_name!r} not implemented."
        )

    scope: dict[str, Any] = {**workflow_inputs, **inputs}
    for sid, outs in step_outputs.items():
        for k, v in outs.items():
            scope.setdefault(k, v)

    resolved_bindings = {
        k: _substitute_template(v, scope)
        for k, v in step.executor.parameter_bindings.items()
    }

    if dry_run_engine:
        handle = {
            "engine_name": engine_name,
            "job_id": "DRYRUN-" + uuid.uuid4().hex[:8],
            "app_id": resolved_bindings.get("app_id"),
            "app_name": resolved_bindings.get("app_name"),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "raw": {"dry_run": True, "resolved_bindings": resolved_bindings},
        }
        return {step.outputs[0].name: handle}

    from workflows.engines.superbio import adapter as superbio_adapter  # noqa: WPS433

    handle = superbio_adapter.dispatch(resolved_bindings)
    return {step.outputs[0].name: handle}


def run_workflow(spec_path: Path, *, workflow_inputs: dict[str, Any], dry_run_engine: bool):
    spec = load_workflow_spec(spec_path)

    base_dir = REPO_ROOT
    run_dir, run_id = _materialize_run_dir(spec, base_dir)

    print(f"[run_workflow] workflow={spec.workflow_id} v{spec.version}")
    print(f"[run_workflow] run_id={run_id}")
    print(f"[run_workflow] run_dir={run_dir}")

    # Apply parameter defaults for any missing optional inputs.
    for opt in spec.optional_inputs:
        if opt.name not in workflow_inputs and opt.default is not None:
            workflow_inputs[opt.name] = opt.default

    context = StepContext(
        base_dir=str(base_dir),
        run_dir=str(run_dir),
        workflow_id=spec.workflow_id,
        run_id=run_id,
    )

    step_outputs: dict[str, dict[str, Any]] = {}
    for step in spec.steps:
        print(f"\n[run_workflow] step={step.id} ({step.executor.executor_type})")
        inputs = _resolve_step_inputs(step, workflow_inputs, step_outputs)
        if step.executor.executor_type == "python":
            outs = _execute_python_step(step, inputs, context)
        elif step.executor.executor_type == "external_engine":
            outs = _execute_external_engine_step(
                step, inputs, workflow_inputs, step_outputs, dry_run_engine
            )
            if dry_run_engine:
                step_outputs[step.id] = outs
                for k, v in outs.items():
                    preview = json.dumps(v, default=str)[:120]
                    print(f"    {k} = {preview}")
                print(
                    f"\n[run_workflow] --dry-run-engine: stopping after step "
                    f"'{step.id}' (no real job to poll/download)."
                )
                break
        else:
            raise NotImplementedError(
                f"executor_type {step.executor.executor_type!r} not supported."
            )
        step_outputs[step.id] = outs
        for k, v in outs.items():
            preview = (
                json.dumps(v, default=str)[:120]
                if not isinstance(v, str) else v[:120]
            )
            print(f"    {k} = {preview}")

    summary = {
        "workflow_id": spec.workflow_id,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "step_outputs": {
            sid: {
                k: (str(v) if isinstance(v, (Path,)) else v)
                for k, v in outs.items()
            }
            for sid, outs in step_outputs.items()
        },
    }
    summary_path = run_dir / "workflow_run.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n[run_workflow] wrote {summary_path}")
    return summary


def _parse_kv_list(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"expected key=value, got {item!r}")
        k, _, v = item.partition("=")
        out[k.strip()] = v.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec", type=Path, help="Path to a workflow spec YAML.")
    ap.add_argument("--input", action="append", default=[],
                    help="key=value workflow input (artifact path or string).")
    ap.add_argument("--param", action="append", default=[],
                    help="key=value workflow parameter override.")
    ap.add_argument("--dry-run-engine", action="store_true",
                    help="Skip the real Superbio submission and emit a DRYRUN job_id.")
    args = ap.parse_args()

    inputs = _parse_kv_list(args.input)
    inputs.update(_parse_kv_list(args.param))

    run_workflow(args.spec, workflow_inputs=inputs, dry_run_engine=args.dry_run_engine)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
