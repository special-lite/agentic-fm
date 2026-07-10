#!/usr/bin/env python3
"""FMLint CLI — validate FileMaker scripts in fmxmlsnippet XML or HR format.

Usage:
    python3 -m agent.fmlint [file_or_directory] [options]

Examples:
    python3 -m agent.fmlint agent/sandbox/MyScript.xml
    python3 -m agent.fmlint agent/sandbox/
    python3 -m agent.fmlint --format json agent/sandbox/MyScript.xml
    python3 -m agent.fmlint --tier 2 --disable N003,D002 agent/sandbox/
    python3 -m agent.fmlint --custom-functions           # lint CF defs (SL021 SQL check)
    python3 -m agent.fmlint --custom-functions path/to/cf.txt
"""

import argparse
import json
import sys
from pathlib import Path

from .engine import LintRunner
from .config import LintConfig
from .types import Severity


def _resolve_project_root():
    """Discover the project root by walking up from this file."""
    # This file is at agent/fmlint/__main__.py
    # Project root is two levels up from agent/
    here = Path(__file__).resolve().parent
    # agent/fmlint/ -> agent/ -> project_root/
    candidate = here.parent.parent
    if (candidate / "agent" / "catalogs").exists():
        return candidate
    return None


# File extensions recognized as lintable
_LINTABLE_EXTENSIONS = {".xml", ".fmscript", ".hr", ".txt"}


def _collect_files(target: Path) -> list:
    """Collect files to lint from a path."""
    if target.is_file():
        return [target]
    if target.is_dir():
        files = []
        for f in sorted(target.iterdir()):
            if (f.is_file()
                    and not f.name.startswith(".")
                    and f.suffix.lower() in _LINTABLE_EXTENSIONS):
                files.append(f)
        return files
    return []


def _severity_icon(sev: Severity) -> str:
    icons = {
        Severity.ERROR: "FAIL",
        Severity.WARNING: "WARN",
        Severity.INFO: "INFO",
        Severity.HINT: "HINT",
    }
    return icons.get(sev, "????")


def _print_result(result, quiet=False):
    """Print lint results in human-readable format."""
    source = result.source or "(stdin)"
    print(f"\n{'=' * 60}")
    print(f"  {source}")
    print(f"{'=' * 60}")

    if quiet:
        diags = [d for d in result.diagnostics
                 if d.severity in (Severity.ERROR, Severity.WARNING)]
    else:
        diags = result.diagnostics

    for d in diags:
        loc = f"line {d.line}" if d.line > 0 else "file"
        print(f"  {_severity_icon(d.severity)}  [{d.rule_id}] {loc}: {d.message}")

    errors = len(result.errors)
    warnings = len(result.warnings)
    total = len(result.diagnostics)

    if errors == 0:
        summary = "PASSED"
        if warnings:
            summary += f" ({warnings} warning(s))"
        elif total:
            summary += f" ({total} info/hint(s))"
    else:
        summary = f"FAILED ({errors} error(s)"
        if warnings:
            summary += f", {warnings} warning(s)"
        summary += ")"

    print(f"\n  {summary}")


def _print_json(results):
    """Print all results as JSON."""
    output = {
        "files": [r.to_dict() for r in results],
        "summary": {
            "total_files": len(results),
            "files_with_errors": sum(1 for r in results if not r.ok),
            "total_errors": sum(len(r.errors) for r in results),
            "total_warnings": sum(len(r.warnings) for r in results),
        },
    }
    print(json.dumps(output, indent=2))


def _run_custom_functions(runner, args, project_root):
    """Lint custom-function definitions with calc rules (e.g. SL021), then exit.

    Discovers CF calc text (default: agent/xml_parsed/custom_functions_sanitized),
    scans only CFs that contain an ExecuteSQL call, and prints only those with
    findings."""
    spec = args.custom_functions
    if spec == "__default__":
        if not project_root:
            print("Error: --custom-functions needs a path (no project root found)",
                  file=sys.stderr)
            sys.exit(1)
        cf_root = project_root / "agent" / "xml_parsed" / "custom_functions_sanitized"
    else:
        cf_root = Path(spec)
    if not cf_root.exists():
        print(f"Error: {cf_root} does not exist", file=sys.stderr)
        sys.exit(1)

    cf_files = [cf_root] if cf_root.is_file() else sorted(cf_root.rglob("*.txt"))
    results = []
    scanned = 0
    for f in cf_files:
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "executesql" not in content.lower():
            continue
        scanned += 1
        res = runner.lint_calc(content, source=str(f))
        if res.diagnostics:
            results.append(res)

    if args.format == "json":
        _print_json(results)
    else:
        for res in results:
            _print_result(res, args.quiet)
        flagged = sum(1 for r in results if not r.ok)
        print(f"\n{'─' * 60}")
        print(f"  {scanned} custom function(s) with ExecuteSQL scanned: ", end="")
        if scanned == 0:
            print("none found")
        elif flagged == 0:
            print("ALL PASSED")
        else:
            print(f"{flagged} FAILED")
        print()

    has_errors = any(not r.ok for r in results)
    has_warnings = any(r.warnings for r in results)
    sys.exit(1 if has_errors else (2 if has_warnings else 0))


def main():
    parser = argparse.ArgumentParser(
        description="FMLint — FileMaker code linter"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="File or directory to lint (default: agent/sandbox/)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--input-format",
        choices=["xml", "hr"],
        default=None,
        help="Input format (default: auto-detect)",
    )
    parser.add_argument(
        "--tier",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Maximum validation tier (default: auto-detect)",
    )
    parser.add_argument(
        "--context",
        default=None,
        help="Path to CONTEXT.json",
    )
    parser.add_argument(
        "--catalog",
        default=None,
        help="Path to step-catalog-en.json",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to fmlint.config.json override file",
    )
    parser.add_argument(
        "--disable",
        default=None,
        help="Comma-separated rule IDs to disable (e.g. N003,D002)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only show errors and warnings",
    )
    parser.add_argument(
        "--custom-functions",
        nargs="?",
        const="__default__",
        default=None,
        help="Lint custom-function definitions with calc rules (SL021) instead of "
             "scripts. Optional path; defaults to agent/xml_parsed/custom_functions_sanitized. "
             "Only CFs containing an ExecuteSQL call are scanned; only CFs with findings print.",
    )

    args = parser.parse_args()

    # Resolve paths
    project_root = _resolve_project_root()

    cf_mode = args.custom_functions is not None

    target = Path(args.path) if args.path else None
    if target is None and not cf_mode and project_root:
        target = project_root / "agent" / "sandbox"
    elif target is None and not cf_mode:
        print("Error: no file or directory specified", file=sys.stderr)
        sys.exit(1)

    if target is not None and not target.exists():
        print(f"Error: {target} does not exist", file=sys.stderr)
        sys.exit(1)

    # Build config from files + CLI overrides
    config_path = Path(args.config) if args.config else None
    config = LintConfig.load(project_root, config_path)
    if args.disable:
        config.disabled_rules = set(args.disable.split(","))
    if args.tier is not None:
        config.max_tier = args.tier

    # Report config validation warnings
    if config.config_warnings and args.format == "text":
        print("Config warnings:", file=sys.stderr)
        for w in config.config_warnings:
            print(f"  - {w}", file=sys.stderr)

    # Build runner
    catalog_path = Path(args.catalog) if args.catalog else None
    context_path = Path(args.context) if args.context else None

    runner = LintRunner(
        project_root=project_root,
        catalog_path=catalog_path,
        context_path=context_path,
        config=config,
    )

    # Custom-function mode: lint CF definitions with calc rules (e.g. SL021), then exit.
    if cf_mode:
        _run_custom_functions(runner, args, project_root)

    # Collect and lint files
    files = _collect_files(target)
    if not files:
        if args.format == "text":
            print(f"No files found in {target}")
        sys.exit(0)

    results = []
    for filepath in files:
        result = runner.lint_file(str(filepath), fmt=args.input_format)
        results.append(result)

    # Output
    if args.format == "json":
        _print_json(results)
    else:
        if runner.tier >= 2 and runner.context.available:
            print(f"CONTEXT.json loaded (tier {runner.tier})")

        for result in results:
            _print_result(result, args.quiet)

        # Summary
        failed = sum(1 for r in results if not r.ok)
        print(f"\n{'─' * 60}")
        print(f"  {len(results)} file(s) linted: ", end="")
        if failed == 0:
            print("ALL PASSED")
        else:
            print(f"{failed} FAILED, {len(results) - failed} passed")
        print()

    # Exit code: 1 if errors, 2 if only warnings, 0 if clean
    has_errors = any(not r.ok for r in results)
    has_warnings = any(r.warnings for r in results)
    if has_errors:
        sys.exit(1)
    elif has_warnings:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
