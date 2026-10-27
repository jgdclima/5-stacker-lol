"""
Relaunch utility for the League of Legends 5-Stack Coordinator Discord Bot.

Responsibilities:
1. Detects whether any slash command definitions (names, descriptions, options,
   choices, or permissions) have changed since the last Discord sync.
2. Stops any currently running `bot.py` process(es) cleanly.
3. Relaunches `bot.py` and, only when slash command changes are detected (or when
   `--sync` / `--force-sync` is passed), triggers re-registration with Discord.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from typing import List

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(PROJECT_ROOT, "data", "bot.pid")
LOG_FILE = os.path.join(PROJECT_ROOT, "data", "bot.log")


def get_python_executable() -> str:
    """Prefer the project's .venv Python interpreter if available."""
    if os.name == "nt":
        venv_py = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
    else:
        venv_py = os.path.join(PROJECT_ROOT, ".venv", "bin", "python")
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable


def find_running_bot_pids() -> List[int]:
    """Find PIDs of any currently running python processes executing bot.py."""
    my_pid = os.getpid()
    pids = set()

    # Check stored PID file first
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                stored_pid = int(f.read().strip())
            if stored_pid != my_pid:
                pids.add(stored_pid)
        except Exception:
            pass

    if os.name == "nt":
        try:
            ps_cmd = (
                "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%'\" | "
                "Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress"
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout.strip())
                if isinstance(data, dict):
                    data = [data]
                for proc in data:
                    pid = proc.get("ProcessId")
                    cmdline = (proc.get("CommandLine") or "").lower()
                    if (
                        pid
                        and pid != my_pid
                        and "bot.py" in cmdline
                        and "relaunch.py" not in cmdline
                    ):
                        pids.add(int(pid))
        except Exception as e:
            print(f"[Warn] Process discovery warning: {e}")
    else:
        try:
            res = subprocess.run(
                ["pgrep", "-f", "bot.py"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    if line.strip().isdigit():
                        pid = int(line.strip())
                        if pid != my_pid:
                            pids.add(pid)
        except Exception:
            pass

    return sorted(pids)


def stop_running_bot() -> int:
    """Terminate all running bot.py processes and wait for them to exit."""
    pids = find_running_bot_pids()
    if not pids:
        print("ℹ️  No existing bot.py process found running.")
        return 0

    print(f"🛑 Stopping existing bot.py process(es): {', '.join(str(p) for p in pids)}...")
    for pid in pids:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
            )
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    # Wait briefly to confirm termination
    deadline = time.time() + 5.0
    while time.time() < deadline:
        remaining = find_running_bot_pids()
        if not remaining:
            break
        time.sleep(0.25)

    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except OSError:
            pass

    print("✅ Previous bot instance(s) stopped.")
    return len(pids)


def inspect_slash_commands(force_sync: bool = False) -> dict:
    """Import bot command tree and check if slash commands require Discord re-registration."""
    sys.path.insert(0, PROJECT_ROOT)
    import bot as bot_module

    diff = bot_module.detect_slash_command_changes(bot_module.bot.tree)
    total = len(diff["payloads"])
    short_hash = diff["current_hash"][:8]

    print("─── Slash Command Registration Check ───")
    if force_sync:
        print(f"🔄 Forced sync enabled: Will re-register all {total} slash commands with Discord (hash: {short_hash}).")
    elif diff["first_run"]:
        print(f"🆕 No cached command state found: Will register {total} slash commands with Discord (hash: {short_hash}).")
    elif diff["changed"]:
        print(f"🔄 Slash command changes detected (previous: {(diff['previous_hash'] or '')[:8]} -> current: {short_hash}):")
        for name in diff["added"]:
            print(f"   + /{name} (added)")
        for name in diff["modified"]:
            print(f"   ~ /{name} (modified options/description/permissions)")
        for name in diff["removed"]:
            print(f"   - /{name} (removed)")
        print("   => Will re-register slash commands with Discord on startup.")
    else:
        print(f"✅ No changes to slash commands ({total} commands, hash: {short_hash}).")
        print("   => Skipping Discord command re-registration.")
    print("────────────────────────────────────────")

    return diff


def launch_bot(needs_sync: bool, foreground: bool = False, startup_timeout: float = 30.0) -> int:
    """Launch bot.py either in the foreground or detached in the background with startup verification."""
    os.makedirs(os.path.join(PROJECT_ROOT, "data"), exist_ok=True)
    python_exe = get_python_executable()
    bot_script = os.path.join(PROJECT_ROOT, "bot.py")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if needs_sync:
        env["FORCE_COMMAND_SYNC"] = "1"
    else:
        env["FORCE_COMMAND_SYNC"] = "0"

    cmd = [python_exe, "-u", bot_script]
    if needs_sync:
        cmd.append("--sync")

    if foreground:
        print(f"🚀 Launching bot.py in foreground ({python_exe})...")
        proc = subprocess.Popen(cmd, cwd=PROJECT_ROOT, env=env)
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
        try:
            return proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            return 0

    print(f"🚀 Launching bot.py in background ({python_exe})...")
    log_handle = open(LOG_FILE, "w", encoding="utf-8", buffering=1)

    creationflags = 0
    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )

    proc = subprocess.Popen(
        cmd,
        cwd=PROJECT_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        start_new_session=(os.name != "nt"),
    )

    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))

    print(f"⏳ Waiting for bot (PID {proc.pid}) to connect to Discord...")
    start_time = time.time()
    ready_completed = False

    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as reader:
        while time.time() - start_time < startup_timeout:
            line = reader.readline()
            if line:
                clean = line.rstrip()
                print(f"   [bot] {clean}")
                if (
                    "Synced " in clean
                    or "Slash commands unchanged" in clean
                    or "Failed to sync commands" in clean
                ):
                    ready_completed = True
                    break
            else:
                if proc.poll() is not None:
                    print(f"❌ Bot process exited prematurely with code {proc.returncode}.")
                    return proc.returncode or 1
                time.sleep(0.2)

    if ready_completed:
        print(f"✅ Bot is online and running in the background (PID: {proc.pid}, Logs: data/bot.log).")
        return 0
    else:
        print(f"⚠️ Startup wait timed out after {startup_timeout:.0f}s, but bot process (PID: {proc.pid}) is running (Logs: data/bot.log).")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Relaunch the 5-Stack Coordinator Discord Bot and conditionally sync slash commands."
    )
    parser.add_argument(
        "--sync",
        "--force-sync",
        dest="force_sync",
        action="store_true",
        help="Force re-registering slash commands with Discord even if no schema changes were detected.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check if slash commands have changed without stopping or relaunching the bot.",
    )
    parser.add_argument(
        "--stop-only",
        action="store_true",
        help="Only stop any running bot.py processes and exit.",
    )
    parser.add_argument(
        "-f",
        "--foreground",
        action="store_true",
        help="Run the bot in the foreground instead of detaching after startup verification.",
    )
    args = parser.parse_args()

    # Ensure UTF-8 console output on Windows
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if args.stop_only:
        stop_running_bot()
        return 0

    diff = inspect_slash_commands(force_sync=args.force_sync)
    if args.check_only:
        return 0

    stop_running_bot()
    needs_sync = args.force_sync or diff["changed"]
    return launch_bot(needs_sync=needs_sync, foreground=args.foreground)


if __name__ == "__main__":
    sys.exit(main())
