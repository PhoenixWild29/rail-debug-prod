import os
import re
from typing import List, Dict, Any, Optional
from collections import Counter
from dataclasses import dataclass

try:
    from core.project import get_project_profile
    from core.memory import get_repo_stats
except ImportError:
    # Fallback for testing
    class DummyProfile:
        languages = []
        frameworks = []
    get_project_profile = lambda p: DummyProfile()
    get_repo_stats = lambda r: {}

@dataclass
class RepoProfile:
    name: str
    path: str
    profile: Any
    memory_stats: Dict[str, Any]

@dataclass
class MultiScanReport:
    repos: List[RepoProfile]
    cross_summary: Dict[str, Any]

def scan_multi_repos(repo_paths: List[str], use_memory: bool = True) -> MultiScanReport:
    repos = []
    all_langs = set()
    all_frameworks = Counter()
    for path in repo_paths:
        abs_path = os.path.abspath(path)
        name = os.path.basename(abs_path.rstrip('/'))
        try:
            profile = get_project_profile(abs_path)
            stats = get_repo_stats(name) if use_memory else {}
            r = RepoProfile(name=name, path=abs_path, profile=profile, memory_stats=stats)
            repos.append(r)
            all_langs |= set(getattr(profile, 'languages', []))
            all_frameworks.update(getattr(profile, 'frameworks', []))
        except Exception as e:
            print(f"Skipped {name}: {e}", file=sys.stderr)
            continue
    summary = {
        "total_repos": len(repos),
        "unique_languages": list(all_langs),
        "framework_counts": dict(all_frameworks),
        "total_analyses": sum(r.memory_stats.get("total_analyses", 0) for r in repos),
        "avg_confidence": sum(r.memory_stats.get("avg_confidence", 0) * r.memory_stats.get("total_analyses", 0) for r in repos) / max(sum(r.memory_stats.get("total_analyses", 0) for r in repos), 1),
    }
    return MultiScanReport(repos=repos, cross_summary=summary)

def parse_portfolio_repos() -> List[str]:
    tools_md = "/Users/phoenixwild/.openclaw/workspace/TOOLS.md"
    repos = ["/Users/phoenixwild/rail-debug-prod"]  # fallback
    if not os.path.exists(tools_md):
        return repos
    with open(tools_md, 'r') as f:
        content = f.read()
    matches = re.findall(r'|\\s*([ ^\\| ]+?)\\s*\\| \\s*([ ^\\| ]+?)\\s*\\| \\s*([ ^\\| ]+?)\\s*\\|', content)
    for repo_name, path_str, _ in matches:
        path = path_str.strip()
        if path.lower() != "tbd" and os.path.exists(path) and os.path.isdir(path):
            repos.append(path)
    return list(set(repos))

def find_repos_in_dir(dir_path: str) -> List[str]:
    repos = []
    abs_dir = os.path.abspath(dir_path)
    for item in os.listdir(abs_dir):
        git_path = os.path.join(abs_dir, item, ".git")
        if os.path.isdir(git_path):
            repos.append(os.path.join(abs_dir, item))
    return repos

def format_multi_pretty(report: MultiScanReport) -> str:
    from textwrap import dedent
    output = dedent("""
    ╔══════════════════════════════════════════════════════╗
    ║  📊 RAIL DEBUG — Multi-Repo Orchestrator Report      ║
    ╚══════════════════════════════════════════════════════╝

    Total Repos: {}
    Languages: {}
    Total Memory Analyses: {}
    """).strip().format(
        report.cross_summary['total_repos'],
        ', '.join(report.cross_summary['unique_languages']),
        report.cross_summary['total_analyses']
    )
    for r in report.repos:
        output += f"\\n\\n📦 {r.name} ({r.path})"
        output += f"\\n  Languages: {', '.join(getattr(r.profile, 'languages', []))}"
        output += f"\\n  Frameworks: {', '.join(getattr(r.profile, 'frameworks', [])[:5])}"
        stats = r.memory_stats
        output += f"\\n  Analyses: {stats.get('total_analyses', 0)}, Success Rate: {stats.get('success_rate', 0):.1%}"
    return output

# Stub for JSON/MD
def report_to_json(report: MultiScanReport) -> str:
    import json
    data = {
        "cross_summary": report.cross_summary,
        "repos": [{
            "name": r.name,
            "path": r.path,
            "profile": vars(r.profile) if hasattr(r.profile, '__dict__') else str(r.profile),
            "memory_stats": r.memory_stats
        } for r in report.repos]
    }
    return json.dumps(data, indent=2, default=str)

def report_to_md(report: MultiScanReport) -> str:
    md = "# Multi-Repo Report\\n\\n"
    md += f"**Total Repos:** {report.cross_summary['total_repos']}\\n"
    md += f"**Languages:** {', '.join(report.cross_summary['unique_languages'])}\\n\\n"
    for r in report.repos:
        md += f"## {r.name}\\n"
        md += f"- Path: {r.path}\\n"
        md += f"- Languages: {', '.join(getattr(r.profile, 'languages', []))}\\n"
        md += f"- Memory: {r.memory_stats}\\n\\n"
    return md