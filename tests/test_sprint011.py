"""
Sprint 011 Tests — IDE & CI Integration.

All tests run fully offline (no API keys required):
  - Tier 1 regex analysis for functional tests
  - File/structure assertions for action + extension assets
  - YAML parsing for CI/action manifest validation
"""

import ast
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.analyzer import analyze


# ── GitHub Action ─────────────────────────────────────────────────

class TestGitHubAction:
    ACTION_DIR = REPO_ROOT / ".github" / "actions" / "rail-debug"

    def test_action_yml_exists(self):
        assert (self.ACTION_DIR / "action.yml").exists()

    def test_run_analysis_py_exists(self):
        assert (self.ACTION_DIR / "run_analysis.py").exists()

    def test_action_yml_structure(self):
        with open(self.ACTION_DIR / "action.yml") as f:
            data = yaml.safe_load(f)
        assert data["name"] == "Rail Debug — AI Error Analyzer"
        assert "inputs" in data
        assert "outputs" in data
        # Required inputs
        assert "traceback" in data["inputs"]
        assert "mode" in data["inputs"]
        assert "fail_on_critical" in data["inputs"]
        # Required outputs
        assert "severity" in data["outputs"]
        assert "tier" in data["outputs"]
        assert "root_cause" in data["outputs"]
        assert "suggested_fix" in data["outputs"]

    def test_action_uses_composite_runner(self):
        with open(self.ACTION_DIR / "action.yml") as f:
            data = yaml.safe_load(f)
        assert data["runs"]["using"] == "composite"
        steps = data["runs"]["steps"]
        assert len(steps) >= 2

    def test_run_analysis_py_valid_syntax(self):
        with open(self.ACTION_DIR / "run_analysis.py") as f:
            source = f.read()
        ast.parse(source)  # raises SyntaxError if invalid

    def test_run_analysis_py_has_write_output(self):
        with open(self.ACTION_DIR / "run_analysis.py") as f:
            source = f.read()
        assert "write_output" in source
        assert "GITHUB_OUTPUT" in source

    def test_run_analysis_py_imports_core_analyzer(self):
        with open(self.ACTION_DIR / "run_analysis.py") as f:
            source = f.read()
        assert "from core.analyzer import analyze" in source


# ── CI Workflow ───────────────────────────────────────────────────

class TestCIWorkflow:
    CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"

    def test_ci_yml_exists(self):
        assert self.CI_YML.exists()

    def test_ci_targets_master_not_main(self):
        with open(self.CI_YML) as f:
            data = yaml.safe_load(f)
        # PyYAML 1.1 quirk: bare `on:` is parsed as boolean True
        triggers = data.get("on") or data.get(True, {})
        push_branches = triggers["push"]["branches"]
        pr_branches = triggers["pull_request"]["branches"]
        assert "master" in push_branches, "CI push must target master"
        assert "master" in pr_branches, "CI PR must target master"
        assert "main" not in push_branches, "CI must not target 'main' (wrong branch)"

    def test_ci_has_test_job(self):
        with open(self.CI_YML) as f:
            data = yaml.safe_load(f)
        assert "test" in data["jobs"]

    def test_ci_has_rail_debug_demo_job(self):
        with open(self.CI_YML) as f:
            data = yaml.safe_load(f)
        assert "rail-debug-demo" in data["jobs"]

    def test_ci_demo_uses_local_action(self):
        with open(self.CI_YML) as f:
            data = yaml.safe_load(f)
        steps = data["jobs"]["rail-debug-demo"]["steps"]
        action_steps = [s for s in steps if s.get("uses", "").startswith("./.github/actions/rail-debug")]
        assert len(action_steps) >= 1, "CI demo job must use the custom rail-debug action"


# ── VS Code Extension ─────────────────────────────────────────────

class TestVSCodeExtension:
    EXT_DIR = REPO_ROOT / "vscode-extension"

    def test_package_json_exists(self):
        assert (self.EXT_DIR / "package.json").exists()

    def test_extension_js_exists(self):
        assert (self.EXT_DIR / "src" / "extension.js").exists()

    def test_vscodeignore_exists(self):
        assert (self.EXT_DIR / ".vscodeignore").exists()

    def test_package_json_valid_json(self):
        with open(self.EXT_DIR / "package.json") as f:
            pkg = json.load(f)
        assert pkg["name"] == "rail-debug"
        assert "engines" in pkg
        assert "vscode" in pkg["engines"]

    def test_package_json_has_required_commands(self):
        with open(self.EXT_DIR / "package.json") as f:
            pkg = json.load(f)
        commands = {c["command"] for c in pkg["contributes"]["commands"]}
        assert "rail-debug.analyze" in commands
        assert "rail-debug.analyzeDeep" in commands
        assert "rail-debug.checkServer" in commands

    def test_package_json_has_configuration(self):
        with open(self.EXT_DIR / "package.json") as f:
            pkg = json.load(f)
        props = pkg["contributes"]["configuration"]["properties"]
        assert "railDebug.serverUrl" in props
        assert "railDebug.defaultMode" in props

    def test_package_json_has_keybinding(self):
        with open(self.EXT_DIR / "package.json") as f:
            pkg = json.load(f)
        keybindings = pkg["contributes"].get("keybindings", [])
        assert any(kb["command"] == "rail-debug.analyze" for kb in keybindings)

    def test_extension_js_exports_activate_deactivate(self):
        with open(self.EXT_DIR / "src" / "extension.js") as f:
            source = f.read()
        assert "function activate" in source
        assert "function deactivate" in source
        assert "module.exports" in source

    def test_extension_js_has_post_json(self):
        with open(self.EXT_DIR / "src" / "extension.js") as f:
            source = f.read()
        assert "postJSON" in source
        assert "/analyze" in source

    def test_extension_js_has_tier_labels(self):
        with open(self.EXT_DIR / "src" / "extension.js") as f:
            source = f.read()
        assert "Grok Fast" in source
        assert "Claude Haiku" in source
        assert "Claude Sonnet" in source


# ── Functional: Tier 1 analysis (offline) ────────────────────────

class TestTier1AnalysisOffline:
    """Verify the analyzer works without any API keys (Tier 1 regex only)."""

    def _analyze(self, traceback):
        return analyze(traceback_text=traceback, deep=False, haiku=False, no_git=True)

    def test_keyerror_resolves_tier1(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        report = self._analyze(
            "Traceback (most recent call last):\n  File 'a.py', line 1\nKeyError: 'missing_key'"
        )
        assert report.tier == 1
        assert report.severity in ("medium", "high", "critical", "low", "info")

    def test_module_not_found_resolves_tier1(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        report = self._analyze(
            "Traceback (most recent call last):\n  File 'app.py', line 1\nModuleNotFoundError: No module named 'requests'"
        )
        assert report.tier == 1
        assert "requests" in report.root_cause or "requests" in report.suggested_fix

    def test_connection_refused_resolves_tier1(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        report = self._analyze(
            "Traceback (most recent call last):\n  File 'server.py', line 10\nConnectionRefusedError: [Errno 111] Connection refused"
        )
        assert report.tier == 1
        assert report.severity in ("critical", "high")
