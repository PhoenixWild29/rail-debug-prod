"""
Project-Aware Mode — Automatic Repo Intelligence for Rail Debug.

Scans a project directory to extract:
- Language & framework detection
- Dependency manifest parsing (requirements.txt, package.json, Cargo.toml, etc.)
- Project structure mapping
- Config file detection (.env, docker-compose, CI configs)
- Entry point identification

Injects structured project context into LLM prompts so fixes are
copy-paste accurate with real package names and versions.
"""

import os
import re
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class ProjectProfile:
    """Complete project intelligence profile."""
    root_path: str
    name: str
    languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    dependencies: Dict[str, str] = field(default_factory=dict)  # name → version
    dev_dependencies: Dict[str, str] = field(default_factory=dict)
    entry_points: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    structure: Dict[str, Any] = field(default_factory=dict)
    runtime: Optional[str] = None  # e.g., "python 3.11", "node 20"
    package_manager: Optional[str] = None  # pip, npm, yarn, cargo, etc.

    def format_for_prompt(self) -> str:
        """Format project profile for LLM injection."""
        sections = []
        sections.append(f"Project: {self.name}")
        sections.append(f"Root: {self.root_path}")

        if self.languages:
            sections.append(f"Languages: {', '.join(self.languages)}")
        if self.frameworks:
            sections.append(f"Frameworks: {', '.join(self.frameworks)}")
        if self.runtime:
            sections.append(f"Runtime: {self.runtime}")
        if self.package_manager:
            sections.append(f"Package Manager: {self.package_manager}")

        if self.dependencies:
            dep_lines = [f"  {k}=={v}" if v else f"  {k}" for k, v in sorted(self.dependencies.items())]
            # Cap at 30 deps to avoid token bloat
            if len(dep_lines) > 30:
                dep_lines = dep_lines[:30] + [f"  ... and {len(dep_lines) - 30} more"]
            sections.append("Dependencies:\n" + "\n".join(dep_lines))

        if self.entry_points:
            sections.append(f"Entry Points: {', '.join(self.entry_points[:5])}")

        if self.config_files:
            sections.append(f"Config Files: {', '.join(self.config_files[:10])}")

        if self.structure:
            sections.append(f"Structure: {json.dumps(self.structure, indent=2)}")

        return "\n".join(sections)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Manifest Parsers ─────────────────────────────────────────────

def _parse_requirements_txt(path: str) -> Dict[str, str]:
    """Parse Python requirements.txt → {package: version}."""
    deps = {}
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                # Handle ==, >=, ~=, <=, !=
                match = re.match(r'^([a-zA-Z0-9_.-]+)\s*(?:[><=!~]+\s*(.+))?', line)
                if match:
                    name = match.group(1).lower()
                    version = match.group(2) or ""
                    deps[name] = version.strip()
    except (IOError, OSError):
        pass
    return deps


def _parse_pyproject_toml(path: str) -> Dict[str, Any]:
    """Parse pyproject.toml for dependencies and project metadata."""
    result = {"deps": {}, "dev_deps": {}, "frameworks": [], "name": None}
    try:
        with open(path, "r") as f:
            content = f.read()

        # Extract project name
        name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
        if name_match:
            result["name"] = name_match.group(1)

        # Extract dependencies block
        in_deps = False
        in_dev_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "[project.dependencies]" or stripped == "dependencies = [":
                in_deps = True
                in_dev_deps = False
                continue
            if "dev-dependencies" in stripped or "dev_dependencies" in stripped:
                in_dev_deps = True
                in_deps = False
                continue
            if stripped.startswith("[") and not stripped.startswith("[["):
                in_deps = False
                in_dev_deps = False
                continue

            # Parse dependency lines
            dep_match = re.match(r'"?([a-zA-Z0-9_.-]+)\s*(?:[><=!~]+\s*(.+?))?"?,?$', stripped)
            if dep_match and (in_deps or in_dev_deps):
                name = dep_match.group(1).lower()
                version = dep_match.group(2) or ""
                if in_dev_deps:
                    result["dev_deps"][name] = version.strip().rstrip('"')
                else:
                    result["deps"][name] = version.strip().rstrip('"')

        # Framework detection from deps
        framework_markers = {
            "fastapi": "FastAPI", "flask": "Flask", "django": "Django",
            "starlette": "Starlette", "tornado": "Tornado", "sanic": "Sanic",
            "pytest": "pytest", "langchain": "LangChain", "langgraph": "LangGraph",
        }
        all_deps = {**result["deps"], **result["dev_deps"]}
        for pkg, fw in framework_markers.items():
            if pkg in all_deps:
                result["frameworks"].append(fw)

    except (IOError, OSError):
        pass
    return result


def _parse_package_json(path: str) -> Dict[str, Any]:
    """Parse Node.js package.json."""
    result = {"deps": {}, "dev_deps": {}, "frameworks": [], "name": None, "runtime": None}
    try:
        with open(path, "r") as f:
            data = json.load(f)

        result["name"] = data.get("name")
        result["deps"] = data.get("dependencies", {})
        result["dev_deps"] = data.get("devDependencies", {})

        # Engine detection
        engines = data.get("engines", {})
        if "node" in engines:
            result["runtime"] = f"node {engines['node']}"

        # Framework detection
        framework_markers = {
            "express": "Express", "next": "Next.js", "react": "React",
            "vue": "Vue", "angular": "Angular", "nestjs": "NestJS",
            "@nestjs/core": "NestJS", "fastify": "Fastify", "koa": "Koa",
            "svelte": "Svelte", "nuxt": "Nuxt", "remix": "Remix",
            "electron": "Electron", "jest": "Jest", "mocha": "Mocha",
        }
        all_deps = {**result["deps"], **result["dev_deps"]}
        for pkg, fw in framework_markers.items():
            if pkg in all_deps:
                result["frameworks"].append(fw)

    except (IOError, OSError, json.JSONDecodeError):
        pass
    return result


def _parse_cargo_toml(path: str) -> Dict[str, Any]:
    """Parse Rust Cargo.toml."""
    result = {"deps": {}, "dev_deps": {}, "frameworks": [], "name": None}
    try:
        with open(path, "r") as f:
            content = f.read()

        # Package name
        name_match = re.search(r'\[package\].*?name\s*=\s*"([^"]+)"', content, re.DOTALL)
        if name_match:
            result["name"] = name_match.group(1)

        # Dependencies
        in_deps = False
        in_dev_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "[dependencies]":
                in_deps = True
                in_dev_deps = False
                continue
            if stripped == "[dev-dependencies]":
                in_dev_deps = True
                in_deps = False
                continue
            if stripped.startswith("[") and stripped not in ("[dependencies]", "[dev-dependencies]"):
                in_deps = False
                in_dev_deps = False
                continue

            dep_match = re.match(r'([a-zA-Z0-9_-]+)\s*=\s*"([^"]+)"', stripped)
            if not dep_match:
                dep_match = re.match(r'([a-zA-Z0-9_-]+)\s*=\s*\{.*version\s*=\s*"([^"]+)"', stripped)
            if dep_match and (in_deps or in_dev_deps):
                name = dep_match.group(1)
                version = dep_match.group(2)
                if in_dev_deps:
                    result["dev_deps"][name] = version
                else:
                    result["deps"][name] = version

        # Framework detection
        framework_markers = {
            "actix-web": "Actix Web", "rocket": "Rocket", "axum": "Axum",
            "tokio": "Tokio", "warp": "Warp", "diesel": "Diesel",
            "sqlx": "SQLx", "serde": "Serde",
        }
        all_deps = {**result["deps"], **result["dev_deps"]}
        for pkg, fw in framework_markers.items():
            if pkg in all_deps:
                result["frameworks"].append(fw)

    except (IOError, OSError):
        pass
    return result


def _parse_go_mod(path: str) -> Dict[str, Any]:
    """Parse Go go.mod."""
    result = {"deps": {}, "name": None, "runtime": None}
    try:
        with open(path, "r") as f:
            content = f.read()

        # Module name
        mod_match = re.search(r'^module\s+(\S+)', content, re.MULTILINE)
        if mod_match:
            result["name"] = mod_match.group(1)

        # Go version
        go_match = re.search(r'^go\s+(\S+)', content, re.MULTILINE)
        if go_match:
            result["runtime"] = f"go {go_match.group(1)}"

        # Dependencies
        in_require = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("require ("):
                in_require = True
                continue
            if stripped == ")" and in_require:
                in_require = False
                continue
            if in_require:
                dep_match = re.match(r'(\S+)\s+(\S+)', stripped)
                if dep_match:
                    result["deps"][dep_match.group(1)] = dep_match.group(2)

    except (IOError, OSError):
        pass
    return result


# ── Structure Scanner ─────────────────────────────────────────────

# Directories to skip during scanning
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", "target",
    ".next", ".nuxt", ".svelte-kit", "coverage", ".eggs", "*.egg-info",
}

# Config files to detect
CONFIG_FILES = {
    ".env", ".env.local", ".env.production",
    "docker-compose.yml", "docker-compose.yaml", "Dockerfile",
    ".github/workflows", "Makefile", "Procfile",
    "tsconfig.json", "jest.config.js", "jest.config.ts",
    "webpack.config.js", "vite.config.ts", "vite.config.js",
    ".eslintrc.json", ".prettierrc", "tox.ini", "setup.cfg",
    "mypy.ini", ".flake8", "rustfmt.toml", "clippy.toml",
}

# Entry point patterns
ENTRY_POINTS = {
    "main.py", "app.py", "server.py", "index.py", "cli.py", "manage.py",
    "index.js", "index.ts", "server.js", "server.ts", "app.js", "app.ts",
    "main.rs", "lib.rs", "main.go", "cmd/main.go",
}


def _scan_structure(root: str, max_depth: int = 3) -> Dict[str, Any]:
    """
    Scan project directory structure (breadth-limited).

    Returns a dict of top-level dirs with file counts and key file flags.
    """
    structure = {}
    root_path = Path(root)

    for item in sorted(root_path.iterdir()):
        if item.name.startswith(".") and item.name not in (".github",):
            continue
        if item.name in SKIP_DIRS:
            continue

        if item.is_file():
            structure[item.name] = "file"
        elif item.is_dir():
            # Count files in subdirectory (1 level)
            try:
                count = sum(1 for f in item.rglob("*") if f.is_file()
                           and not any(skip in f.parts for skip in SKIP_DIRS))
                structure[item.name + "/"] = f"{count} files"
            except (PermissionError, OSError):
                structure[item.name + "/"] = "?"

    return structure


def _detect_entry_points(root: str) -> List[str]:
    """Find common entry point files."""
    found = []
    root_path = Path(root)

    for ep in ENTRY_POINTS:
        ep_path = root_path / ep
        if ep_path.exists():
            found.append(ep)

    # Also check for scripts in package.json
    pkg_json = root_path / "package.json"
    if pkg_json.exists():
        try:
            with open(pkg_json, "r") as f:
                data = json.load(f)
            main = data.get("main")
            if main:
                found.append(f"package.main: {main}")
            scripts = data.get("scripts", {})
            if "start" in scripts:
                found.append(f"npm start: {scripts['start']}")
        except (IOError, json.JSONDecodeError):
            pass

    return found


def _detect_configs(root: str) -> List[str]:
    """Find configuration files present in the project."""
    found = []
    root_path = Path(root)

    for cfg in CONFIG_FILES:
        cfg_path = root_path / cfg
        if cfg_path.exists():
            found.append(cfg)

    # Check for GitHub Actions
    workflows = root_path / ".github" / "workflows"
    if workflows.is_dir():
        for wf in workflows.iterdir():
            if wf.suffix in (".yml", ".yaml"):
                found.append(f".github/workflows/{wf.name}")

    return found


# ── Main Scanner ──────────────────────────────────────────────────

def scan_project(project_path: str) -> ProjectProfile:
    """
    Scan a project directory and build a complete ProjectProfile.

    Args:
        project_path: Path to the project root directory.

    Returns:
        ProjectProfile with all detected metadata.
    """
    root = os.path.abspath(project_path)
    name = os.path.basename(root)
    languages = []
    frameworks = []
    deps = {}
    dev_deps = {}
    runtime = None
    pkg_manager = None

    # ── Python ────────────────────────────────────
    req_txt = os.path.join(root, "requirements.txt")
    pyproject = os.path.join(root, "pyproject.toml")
    setup_py = os.path.join(root, "setup.py")

    if os.path.exists(req_txt):
        languages.append("Python")
        pkg_manager = "pip"
        deps.update(_parse_requirements_txt(req_txt))

    if os.path.exists(pyproject):
        if "Python" not in languages:
            languages.append("Python")
        parsed = _parse_pyproject_toml(pyproject)
        deps.update(parsed["deps"])
        dev_deps.update(parsed["dev_deps"])
        frameworks.extend(parsed["frameworks"])
        if parsed["name"]:
            name = parsed["name"]
        pkg_manager = pkg_manager or "pip"

    if os.path.exists(setup_py) and "Python" not in languages:
        languages.append("Python")
        pkg_manager = pkg_manager or "pip"

    # Check for Poetry
    if os.path.exists(os.path.join(root, "poetry.lock")):
        pkg_manager = "poetry"
    elif os.path.exists(os.path.join(root, "Pipfile")):
        pkg_manager = "pipenv"

    # ── Node.js ───────────────────────────────────
    pkg_json = os.path.join(root, "package.json")
    if os.path.exists(pkg_json):
        languages.append("JavaScript/TypeScript")
        parsed = _parse_package_json(pkg_json)
        deps.update(parsed["deps"])
        dev_deps.update(parsed["dev_deps"])
        frameworks.extend(parsed["frameworks"])
        if parsed["name"]:
            name = parsed["name"]
        if parsed["runtime"]:
            runtime = parsed["runtime"]

        # Detect package manager
        if os.path.exists(os.path.join(root, "pnpm-lock.yaml")):
            pkg_manager = pkg_manager or "pnpm"
        elif os.path.exists(os.path.join(root, "yarn.lock")):
            pkg_manager = pkg_manager or "yarn"
        elif os.path.exists(os.path.join(root, "bun.lockb")):
            pkg_manager = pkg_manager or "bun"
        else:
            pkg_manager = pkg_manager or "npm"

        # TypeScript detection
        if os.path.exists(os.path.join(root, "tsconfig.json")):
            if "JavaScript/TypeScript" in languages:
                languages.remove("JavaScript/TypeScript")
                languages.append("TypeScript")

    # ── Rust ──────────────────────────────────────
    cargo_toml = os.path.join(root, "Cargo.toml")
    if os.path.exists(cargo_toml):
        languages.append("Rust")
        pkg_manager = pkg_manager or "cargo"
        parsed = _parse_cargo_toml(cargo_toml)
        deps.update(parsed["deps"])
        dev_deps.update(parsed["dev_deps"])
        frameworks.extend(parsed["frameworks"])
        if parsed["name"]:
            name = parsed["name"]

    # ── Go ────────────────────────────────────────
    go_mod = os.path.join(root, "go.mod")
    if os.path.exists(go_mod):
        languages.append("Go")
        pkg_manager = pkg_manager or "go modules"
        parsed = _parse_go_mod(go_mod)
        deps.update(parsed["deps"])
        if parsed["name"]:
            name = parsed["name"]
        if parsed["runtime"]:
            runtime = runtime or parsed["runtime"]

    # ── Solidity ──────────────────────────────────
    if any(Path(root).rglob("*.sol")):
        languages.append("Solidity")
        if os.path.exists(os.path.join(root, "hardhat.config.js")) or \
           os.path.exists(os.path.join(root, "hardhat.config.ts")):
            frameworks.append("Hardhat")
        if os.path.exists(os.path.join(root, "foundry.toml")):
            frameworks.append("Foundry")
        if os.path.exists(os.path.join(root, "truffle-config.js")):
            frameworks.append("Truffle")

    # ── Java/Kotlin ───────────────────────────────
    if os.path.exists(os.path.join(root, "pom.xml")):
        languages.append("Java")
        pkg_manager = pkg_manager or "maven"
        frameworks.append("Maven")
    if os.path.exists(os.path.join(root, "build.gradle")) or \
       os.path.exists(os.path.join(root, "build.gradle.kts")):
        if "Java" not in languages:
            languages.append("Java")
        pkg_manager = pkg_manager or "gradle"
        frameworks.append("Gradle")

    # ── Framework detection from deps ─────────────
    framework_markers = {
        "fastapi": "FastAPI", "flask": "Flask", "django": "Django",
        "express": "Express", "react": "React", "next": "Next.js",
        "anthropic": "Anthropic SDK", "openai": "OpenAI SDK",
        "langchain": "LangChain", "langgraph": "LangGraph",
        "solana": "Solana", "anchor-lang": "Anchor",
        "web3": "Web3.js", "ethers": "Ethers.js",
    }
    all_deps = {**deps, **dev_deps}
    for pkg, fw in framework_markers.items():
        if pkg in all_deps and fw not in frameworks:
            frameworks.append(fw)

    # ── Scan structure, entry points, configs ─────
    structure = _scan_structure(root)
    entry_points = _detect_entry_points(root)
    config_files = _detect_configs(root)

    # Deduplicate
    frameworks = list(dict.fromkeys(frameworks))

    return ProjectProfile(
        root_path=root,
        name=name,
        languages=languages,
        frameworks=frameworks,
        dependencies=deps,
        dev_dependencies=dev_deps,
        entry_points=entry_points,
        config_files=config_files,
        structure=structure,
        runtime=runtime,
        package_manager=pkg_manager,
    )


# ── Cache ─────────────────────────────────────────────────────────

_project_cache: Dict[str, ProjectProfile] = {}


def get_project_profile(project_path: str, force_rescan: bool = False) -> ProjectProfile:
    """
    Get or create a cached ProjectProfile for a directory.

    Caches results to avoid re-scanning on every error analysis.
    """
    abs_path = os.path.abspath(project_path)
    if abs_path not in _project_cache or force_rescan:
        _project_cache[abs_path] = scan_project(abs_path)
    return _project_cache[abs_path]


def clear_project_cache():
    """Clear the project profile cache."""
    _project_cache.clear()
