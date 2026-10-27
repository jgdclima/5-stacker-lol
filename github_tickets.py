"""
Automated Discord-to-GitHub Issue creation client.
Supports creating GitHub issues directly via the GitHub REST API (if GITHUB_TOKEN is configured)
with an automatic fallback to the authenticated `gh` CLI (`gh issue create`).
"""

import asyncio
import os
import shutil
from datetime import datetime
from typing import Dict, Any, List, Optional
import aiohttp


DEFAULT_GITHUB_REPO = "jgdclima/5-stacker-lol"

CATEGORY_LABELS: Dict[str, List[str]] = {
    "bug": ["bug"],
    "feature": ["enhancement"],
    "ux": ["enhancement"],
}

CATEGORY_TITLES: Dict[str, str] = {
    "bug": "Bug Report",
    "feature": "Feature Request",
    "ux": "UX / Channel Feedback",
}


class GitHubTicketClient:
    def __init__(
        self,
        repo: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.repo = (repo or os.getenv("GITHUB_REPO") or DEFAULT_GITHUB_REPO).strip()
        self.token = (token if token is not None else os.getenv("GITHUB_TOKEN", "")).strip()

    def format_issue_payload(
        self,
        category: str,
        title: str,
        description: str,
        reporter_name: str,
        reporter_id: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Builds the structured title, Markdown body, and labels for a GitHub issue."""
        norm_cat = category.lower().strip()
        if norm_cat not in CATEGORY_TITLES:
            if "bug" in norm_cat:
                norm_cat = "bug"
            elif "ux" in norm_cat or "noise" in norm_cat:
                norm_cat = "ux"
            else:
                norm_cat = "feature"

        cat_display = CATEGORY_TITLES[norm_cat]
        prefix = "[Bug]" if norm_cat == "bug" else ("[UX]" if norm_cat == "ux" else "[Feature]")
        clean_title = title.strip()
        if not clean_title.lower().startswith(prefix.lower()):
            full_title = f"{prefix} {clean_title}"
        else:
            full_title = clean_title

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        context_line = f"- **Session Context**: `{session_id}`\n" if session_id else ""

        body = (
            f"### {cat_display}\n\n"
            f"{description.strip()}\n\n"
            f"---\n"
            f"#### Metadata\n"
            f"- **Submitted by**: `{reporter_name}` (Discord ID: `{reporter_id}`)\n"
            f"- **Category**: {cat_display}\n"
            f"{context_line}"
            f"- **Submitted at**: `{timestamp}`\n"
            f"- **Source**: 5-Stack Coordinator Discord Bot (`/feedback`)\n"
        )

        labels = list(CATEGORY_LABELS.get(norm_cat, ["enhancement"]))
        return {
            "title": full_title,
            "body": body,
            "labels": labels,
            "category_key": norm_cat,
            "category_display": cat_display,
        }

    async def create_issue(
        self,
        category: str,
        title: str,
        description: str,
        reporter_name: str,
        reporter_id: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a GitHub issue using either the GitHub REST API (if GITHUB_TOKEN is set)
        or the authenticated `gh` CLI.
        Returns:
            {
                "success": bool,
                "url": Optional[str],
                "number": Optional[int],
                "error": Optional[str],
                "title": str,
            }
        """
        payload = self.format_issue_payload(
            category=category,
            title=title,
            description=description,
            reporter_name=reporter_name,
            reporter_id=reporter_id,
            session_id=session_id,
        )

        # 1. Try GitHub REST API if token is configured
        if self.token:
            api_res = await self._create_via_rest_api(payload)
            if api_res["success"]:
                return api_res

        # 2. Fallback to GitHub CLI (`gh issue create`)
        cli_res = await self._create_via_gh_cli(payload)
        return cli_res

    async def _create_via_rest_api(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"https://api.github.com/repos/{self.repo}/issues"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "5-Stack-Coordinator-Discord-Bot",
        }
        req_body = {
            "title": payload["title"],
            "body": payload["body"],
            "labels": payload["labels"],
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=req_body, timeout=15) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        return {
                            "success": True,
                            "url": data.get("html_url"),
                            "number": data.get("number"),
                            "error": None,
                            "title": payload["title"],
                        }
                    # Retry without labels if label validation failed (422)
                    if resp.status == 422 and req_body.get("labels"):
                        req_body.pop("labels", None)
                        async with session.post(url, headers=headers, json=req_body, timeout=15) as retry_resp:
                            if retry_resp.status in (200, 201):
                                data = await retry_resp.json()
                                return {
                                    "success": True,
                                    "url": data.get("html_url"),
                                    "number": data.get("number"),
                                    "error": None,
                                    "title": payload["title"],
                                }
                    err_text = await resp.text()
                    return {
                        "success": False,
                        "url": None,
                        "number": None,
                        "error": f"GitHub API HTTP {resp.status}: {err_text[:200]}",
                        "title": payload["title"],
                    }
        except Exception as e:
            return {
                "success": False,
                "url": None,
                "number": None,
                "error": str(e),
                "title": payload["title"],
            }

    async def _create_via_gh_cli(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        gh_path = shutil.which("gh")
        if not gh_path:
            return {
                "success": False,
                "url": None,
                "number": None,
                "error": "Neither GITHUB_TOKEN nor `gh` CLI is available on the host.",
                "title": payload["title"],
            }

        cmd = [
            gh_path,
            "issue",
            "create",
            "--repo",
            self.repo,
            "--title",
            payload["title"],
            "--body",
            payload["body"],
        ]
        for label in payload.get("labels", []):
            cmd.extend(["--label", label])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
            if proc.returncode != 0 and payload.get("labels"):
                # Retry without --label in case a label doesn't exist in repo
                cmd_no_labels = [
                    gh_path,
                    "issue",
                    "create",
                    "--repo",
                    self.repo,
                    "--title",
                    payload["title"],
                    "--body",
                    payload["body"],
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd_no_labels,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)

            out_str = stdout.decode("utf-8", errors="replace").strip()
            err_str = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode == 0 and out_str:
                issue_url = out_str.splitlines()[-1].strip()
                issue_num = None
                if "/issues/" in issue_url:
                    try:
                        issue_num = int(issue_url.rsplit("/issues/", 1)[-1].strip("/"))
                    except ValueError:
                        pass
                return {
                    "success": True,
                    "url": issue_url,
                    "number": issue_num,
                    "error": None,
                    "title": payload["title"],
                }

            return {
                "success": False,
                "url": None,
                "number": None,
                "error": err_str or f"gh exited with code {proc.returncode}",
                "title": payload["title"],
            }
        except Exception as e:
            return {
                "success": False,
                "url": None,
                "number": None,
                "error": str(e),
                "title": payload["title"],
            }
