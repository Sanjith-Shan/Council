"""
Council Command Analyzer
---------------------
Parses the actual shell command inside OpenClaw's 'exec' tool calls
and classifies them as safe (skip council) or risky (needs evaluation).

This solves the problem: OpenClaw routes almost everything through 'exec',
so we can't just label 'exec' as safe or unsafe — we need to look at
WHAT command is being run.
"""

import re
import shlex

# ── Commands that are always safe (read-only, local, no side effects) ──

SAFE_COMMANDS = {
    # File inspection (read-only)
    "cat", "head", "tail", "less", "more", "wc", "file", "stat",
    "md5sum", "sha256sum", "shasum", "cksum",
    # Directory listing
    "ls", "dir", "tree", "find", "locate", "which", "whereis", "type",
    # Text processing (read-only)
    "grep", "egrep", "fgrep", "awk", "sed", "sort", "uniq", "cut",
    "tr", "diff", "comm", "paste", "column", "fold", "fmt", "nl",
    "tee", "xargs",
    # System info
    "echo", "printf", "date", "cal", "uptime", "hostname", "uname",
    "whoami", "id", "groups", "env", "printenv", "pwd", "df", "du",
    "free", "top", "htop", "ps", "lsof", "nproc", "arch",
    # Development (read-only / local)
    "git status", "git log", "git diff", "git branch", "git show",
    "git remote", "git tag",
    "node --version", "python --version", "python3 --version",
    "npm --version", "pip --version",
    "jq", "yq", "xmllint",
    # Navigation
    "cd", "pushd", "popd",
    # Testing / checking
    "test", "[",
    "true", "false",
}

# Prefixes that make a command safe (e.g., "git log ..." starts with "git log")
SAFE_PREFIXES = [
    "echo ", "printf ", "cat ", "head ", "tail ", "wc ", "ls ",
    "find ", "grep ", "awk ", "sed ", "sort ", "uniq ", "cut ",
    "diff ", "stat ", "file ", "du ", "df ", "pwd",
    "git status", "git log", "git diff", "git branch", "git show",
    "git remote", "git tag",
    "cd ", "test ", "[ ",
]

# ── Commands that are dangerous (destructive, network, install, escalation) ──

DANGEROUS_COMMANDS = {
    # Destructive
    "rm", "rmdir", "shred", "mkfs", "dd",
    # Permission / ownership
    "chmod", "chown", "chgrp", "sudo", "su", "doas",
    # Network (data exfiltration risk)
    "curl", "wget", "nc", "ncat", "netcat", "ssh", "scp", "rsync",
    "ftp", "sftp", "telnet",
    # Package installation
    "pip", "pip3", "npm", "yarn", "pnpm", "apt", "apt-get", "yum",
    "dnf", "brew", "snap", "cargo", "go install",
    # Process control
    "kill", "killall", "pkill", "nohup", "disown",
    # System modification
    "systemctl", "service", "mount", "umount", "iptables",
    "useradd", "userdel", "passwd", "crontab",
    # Code execution (arbitrary)
    "eval", "exec", "source", "python", "python3", "node", "ruby",
    "perl", "bash", "sh", "zsh",
}

DANGEROUS_PATTERNS = [
    r"rm\s+(-[a-zA-Z]*[rf])",          # rm with -r or -f flags
    r"\|\s*(bash|sh|zsh|python)",       # piping into shell
    r">\s*/etc/",                       # writing to /etc
    r">\s*~/\.",                         # writing to dotfiles
    r"curl.*\|",                        # curl piped to anything
    r"wget.*\|",                        # wget piped to anything
    r"chmod\s+[0-7]*7",                 # world-writable permissions
    r":(){ :\|:& };:",                  # fork bomb
    r"/dev/(sd|hd|nvme)",               # raw disk access
    r"\.env",                           # accessing env files
    r"(api.?key|password|secret|token)", # credential access
    r"\$\(.*\)",                        # command substitution (risky in some contexts)
]


def extract_base_command(command_str: str) -> str:
    """Extract the first meaningful command from a shell string.
    Handles: cd /dir; wc -c file → returns 'wc'
    Handles: if [ -f x ]; then echo y; fi → returns 'echo'
    """
    # Strip leading cd commands and directory changes
    command_str = command_str.strip()

    # Handle compound commands: take the last meaningful command
    # Split on ; and && and ||
    parts = re.split(r'[;&|]+', command_str)
    # Filter out cd, test, if/then/else/fi, and empty parts
    skip = {"cd", "if", "then", "else", "elif", "fi", "do", "done",
            "for", "while", "until", "case", "esac", "}", "{", ""}

    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Remove shell conditionals
        part = re.sub(r'^\s*(if|then|else|elif)\s+', '', part)
        part = re.sub(r'\[\s+.*?\]', '', part).strip()

        try:
            tokens = shlex.split(part)
        except ValueError:
            tokens = part.split()

        if not tokens:
            continue

        cmd = tokens[0].strip()

        # Skip shell builtins that aren't the "real" command
        if cmd in skip:
            continue
        # Handle paths like /usr/bin/wc → wc
        if '/' in cmd:
            cmd = cmd.split('/')[-1]
        return cmd

    # Fallback: try the very first word
    try:
        tokens = shlex.split(command_str)
        if tokens:
            cmd = tokens[0]
            if '/' in cmd:
                cmd = cmd.split('/')[-1]
            return cmd
    except ValueError:
        pass

    return command_str.split()[0] if command_str.split() else ""


def classify_command(command_str: str) -> str:
    """Classify a shell command as 'safe', 'dangerous', or 'unknown'.

    safe     → skip the council, auto-execute (Tier 1)
    dangerous → must go through the council
    unknown   → must go through the council (conservative default)
    """
    if not command_str or not command_str.strip():
        return "safe"

    full_cmd = command_str.strip().lower()

    # Check dangerous patterns first (highest priority)
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, full_cmd, re.IGNORECASE):
            return "dangerous"

    # Extract the base command
    base_cmd = extract_base_command(command_str).lower()

    # Check if base command is explicitly dangerous
    if base_cmd in DANGEROUS_COMMANDS:
        return "dangerous"

    # Check if the full command starts with a safe prefix
    for prefix in SAFE_PREFIXES:
        if full_cmd.startswith(prefix) or full_cmd.lstrip().startswith(prefix):
            return "safe"

    # Check if the command after cd/directory change is safe
    # e.g., "cd /some/dir; wc -c file" → check "wc"
    if base_cmd in SAFE_COMMANDS:
        return "safe"

    # Check all parts of a compound command
    parts = re.split(r'[;&|]+', full_cmd)
    all_safe = True
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Remove conditionals
        part = re.sub(r'^\s*(if|then|else|elif)\s+', '', part).strip()
        part = re.sub(r'\[\s+.*?\]\s*;?\s*', '', part).strip()
        if not part or part in ("fi", "done", "esac", "}", "{"):
            continue

        part_cmd = part.split()[0] if part.split() else ""
        if '/' in part_cmd:
            part_cmd = part_cmd.split('/')[-1]

        if part_cmd in DANGEROUS_COMMANDS:
            return "dangerous"
        if part_cmd not in SAFE_COMMANDS and part_cmd not in ("cd", "if", "then", "else", "fi", "[", "test"):
            all_safe = False

    if all_safe:
        return "safe"

    # Default: unknown → send to council
    return "unknown"


def is_exec_safe(tool_name: str, parameters: dict) -> bool:
    """Check if an exec tool call is safe based on the actual command.
    Returns True if the command is safe and can skip the council.
    """
    if tool_name != "exec":
        return False

    command = parameters.get("command", "")
    classification = classify_command(command)
    return classification == "safe"
