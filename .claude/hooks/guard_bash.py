"""PreToolUse guard for Bash/PowerShell commands. Fails closed.

Blocks anything that writes to GitHub (the user owns every remote operation), bypasses
the repo's git hooks, or smuggles AI attribution into commits. ``permissions.deny`` in
``.claude/settings.json`` is the first line of defence; this hook catches compound,
wrapped and nested forms the prefix rules miss. The ``pre-push`` git hook is the backstop.
"""

from __future__ import annotations

import re
import shlex
import sys
from collections.abc import Iterator, Mapping, Sequence
from typing import TextIO

from _common import Decision, HookIO, JsonDict, emit, pretool_decision, read_payload

AI_MARKER_PATTERNS: tuple[str, ...] = (
    r"co-authored-by:[^\n]*\b(?:claude|anthropic)\b",
    r"noreply@anthropic\.com",
    r"generated (?:with|by) \[?claude",
    r"claude\.ai/code",
)
_AI_MARKERS = re.compile("|".join(AI_MARKER_PATTERNS), re.IGNORECASE)

_REMOTE = (
    "Repo policy: Claude never writes to GitHub (push, PRs, issues, releases, settings, API "
    "writes). Ask the user to run this from their own terminal."
)
_BYPASS = "Repo policy: never bypass the git hooks (pre-commit/commit-msg/pre-push) or skip checks."
_ATTRIBUTION = "Repo policy: commits must not carry AI attribution (Claude/Anthropic trailers)."
_MAX_DEPTH = 6

_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_BYPASS_ENV = frozenset({"SKIP", "PRE_COMMIT_ALLOW_NO_CONFIG"})
_PS_BYPASS_ENV = re.compile(r"\$env:(?:SKIP|PRE_COMMIT_ALLOW_NO_CONFIG)\b", re.IGNORECASE)
_SUBSTITUTIONS = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
_GITHUB_HOST = re.compile(r"(?:api|uploads)\.github\.com|(?:^|[/@.])github\.com[/:]", re.IGNORECASE)

# Wrappers that run their arguments as a command: (options that take a value, positionals to skip).
_TRANSPARENT: Mapping[str, tuple[frozenset[str], int]] = {
    "env": (frozenset({"-u", "--unset", "-C", "--chdir"}), 0),
    "command": (frozenset(), 0),
    "builtin": (frozenset(), 0),
    "exec": (frozenset({"-a"}), 0),
    "nohup": (frozenset(), 0),
    "time": (frozenset({"-f", "-o"}), 0),
    "sudo": (frozenset({"-u", "-g", "-C", "-D"}), 0),
    "nice": (frozenset({"-n"}), 0),
    "stdbuf": (frozenset({"-i", "-o", "-e"}), 0),
    "timeout": (frozenset({"-s", "-k", "--signal", "--kill-after"}), 1),
    "xargs": (frozenset({"-n", "-I", "-L", "-P", "-s", "-d", "-E", "-a", "--max-args"}), 0),
}
_UV_RUN_VALUE_OPTS = frozenset(
    {
        "--with",
        "--with-requirements",
        "--python",
        "-p",
        "--project",
        "--directory",
        "--group",
        "--extra",
        "--package",
        "--env-file",
        "--index",
        "--index-url",
        "--from",
    }
)
_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "fish"})
_POWERSHELLS = frozenset({"pwsh", "powershell"})
_EVALUATORS = frozenset({"eval", "iex", "invoke-expression"})

_GIT_VALUE_OPTS = frozenset(
    {
        "-C",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--exec-path",
        "--super-prefix",
        "--config-env",
    }
)
_GIT_CONFIG_READ_FLAGS = frozenset(
    {"--get", "--get-all", "--get-regexp", "--list", "-l", "--show-origin"}
)
_GIT_PROTECTED_KEYS = re.compile(
    r"^(?:alias\.|user\.|remote\.|url\.|credential|core\.hookspath$)", re.I
)
_COMMIT_VALUE_OPTS = frozenset(
    {
        "-m",
        "--message",
        "-F",
        "--file",
        "-C",
        "--reuse-message",
        "-c",
        "--reedit-message",
        "--author",
        "--date",
        "--fixup",
        "--squash",
        "-t",
        "--template",
        "--trailer",
        "--cleanup",
    }
)
_REMOTE_WRITE_ACTIONS = frozenset({"add", "set-url", "rename", "remove", "rm", "set-head"})

_GH_VALUE_OPTS = frozenset({"-R", "--repo", "--hostname"})
_GH_GROUP_AND_ACTION = 2  # e.g. `gh pr create`
_GH_WRITES: Mapping[str, frozenset[str]] = {
    "pr": frozenset(
        {
            "create",
            "merge",
            "edit",
            "comment",
            "review",
            "close",
            "reopen",
            "ready",
            "lock",
            "unlock",
            "update-branch",
        }
    ),
    "issue": frozenset(
        {
            "create",
            "edit",
            "close",
            "comment",
            "reopen",
            "delete",
            "transfer",
            "lock",
            "unlock",
            "pin",
            "unpin",
            "develop",
        }
    ),
    "repo": frozenset(
        {
            "create",
            "edit",
            "delete",
            "fork",
            "rename",
            "archive",
            "unarchive",
            "sync",
            "deploy-key",
            "autolink",
        }
    ),
    "release": frozenset({"create", "edit", "delete", "upload", "delete-asset"}),
    "workflow": frozenset({"run", "enable", "disable"}),
    "run": frozenset({"rerun", "cancel", "delete"}),
    "secret": frozenset({"set", "delete", "remove"}),
    "variable": frozenset({"set", "delete", "remove"}),
    "label": frozenset({"create", "edit", "delete", "clone"}),
    "gist": frozenset({"create", "edit", "delete", "rename"}),
    "cache": frozenset({"delete"}),
    "alias": frozenset({"set", "import", "delete"}),
    "ssh-key": frozenset({"add", "delete"}),
    "gpg-key": frozenset({"add", "delete"}),
    "codespace": frozenset({"create", "delete", "edit", "stop", "rebuild"}),
    "project": frozenset(
        {
            "create",
            "edit",
            "delete",
            "close",
            "copy",
            "link",
            "unlink",
            "item-add",
            "item-create",
            "item-edit",
            "item-delete",
            "item-archive",
            "field-create",
            "field-delete",
            "mark-template",
        }
    ),
}
_GH_API_VALUE_OPTS = frozenset(
    {"-H", "--header", "--jq", "-q", "--template", "-t", "--cache", "-p", "--preview", "--hostname"}
)
_GH_API_FIELD_OPTS = frozenset({"-f", "-F", "--field", "--raw-field", "--input"})

_CURL_DATA_OPTS = frozenset(
    {
        "-d",
        "--data",
        "--data-raw",
        "--data-binary",
        "--data-urlencode",
        "--data-ascii",
        "--json",
        "-F",
        "--form",
        "--form-string",
        "-T",
        "--upload-file",
    }
)
_WGET_DATA_OPTS = ("--post-data", "--post-file", "--body-data", "--body-file")
_PS_HTTP = frozenset({"invoke-restmethod", "irm", "invoke-webrequest", "iwr"})


def evaluate(command: str) -> Decision | None:
    """Return the strictest decision for ``command`` (deny beats ask), or None to allow."""
    decisions = list(_walk(command, 0))
    for kind in ("deny", "ask"):
        for decision in decisions:
            if decision.kind == kind:
                return decision
    return None


def _walk(command: str, depth: int) -> Iterator[Decision]:
    if depth > _MAX_DEPTH:
        yield Decision("deny", "Command nesting is too deep to inspect safely.")
        return
    if _PS_BYPASS_ENV.search(command):
        yield Decision("deny", _BYPASS)
    for match in _SUBSTITUTIONS.finditer(command):
        inner = match.group(1) if match.group(1) is not None else match.group(2)
        if inner and inner.strip():
            yield from _walk(inner, depth + 1)
    for segment in _split_top_level(command):
        argv, assignments = _strip_wrappers(_tokenize(segment))
        if any(a.split("=", 1)[0] in _BYPASS_ENV for a in assignments):
            yield Decision("deny", _BYPASS)
        if not argv:
            continue
        nested = _nested_command(argv)
        if nested is not None:
            if isinstance(nested, Decision):
                yield nested
            else:
                yield from _walk(nested, depth + 1)
            continue
        decision = _analyze(argv, command)
        if decision is not None:
            yield decision


def _split_top_level(command: str) -> list[str]:
    """Split on shell control operators (; | & newline parentheses) outside quotes."""
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(command):
        ch = command[i]
        if quote is not None:
            buf.append(ch)
            if ch == quote:
                quote = None
            elif ch == "\\" and quote == '"' and i + 1 < len(command):
                buf.append(command[i + 1])
                i += 1
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch in ";|&\n()":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [part.strip() for part in parts if part.strip()]


def _tokenize(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def _prog(token: str) -> str:
    name = re.split(r"[\\/]", token)[-1].lower()
    return name.removesuffix(".exe")


def _drop_options(
    tokens: Sequence[str], value_opts: frozenset[str], positionals: int = 0
) -> list[str]:
    rest = list(tokens)
    while rest and rest[0].startswith("-"):
        opt = rest.pop(0)
        if opt in value_opts and rest:
            rest.pop(0)
    return rest[positionals:]


def _strip_wrappers(argv: list[str]) -> tuple[list[str], list[str]]:
    """Drop env assignments and transparent wrappers; return (argv, assignments)."""
    assignments: list[str] = []
    while argv:
        head = _prog(argv[0])
        if _ASSIGNMENT.match(argv[0]):
            assignments.append(argv[0])
            argv = argv[1:]
        elif head in _TRANSPARENT:
            value_opts, positionals = _TRANSPARENT[head]
            argv = _drop_options(argv[1:], value_opts, positionals)
        elif head == "uv" and len(argv) > 1 and argv[1] == "run":
            argv = _drop_options(argv[2:], _UV_RUN_VALUE_OPTS)
        elif head == "pnpm" and len(argv) > 1 and argv[1] in {"exec", "dlx"}:
            argv = argv[2:]
        elif head == "start-process":
            argv = _start_process_argv(argv[1:])
        else:
            break
    return argv, assignments


def _start_process_argv(tokens: Sequence[str]) -> list[str]:
    value_flags = {
        "-workingdirectory",
        "-windowstyle",
        "-verb",
        "-redirectstandardoutput",
        "-redirectstandarderror",
        "-redirectstandardinput",
        "-credential",
    }
    out: list[str] = []
    skip = False
    for token in tokens:
        if skip:
            skip = False
            continue
        low = token.lower()
        if low in value_flags:
            skip = True
        elif not low.startswith("-"):
            out.extend(part for part in token.split(",") if part)
    return out


def _nested_command(argv: list[str]) -> str | Decision | None:  # noqa: PLR0911, PLR0912 (one branch per wrapper kind)
    """Return the inner command string for shells/evaluators, a Decision, or None."""
    prog = _prog(argv[0])
    if prog in _SHELLS:
        for i, token in enumerate(argv[1:], start=1):
            if re.fullmatch(r"-[a-z]*c[a-z]*", token):
                return argv[i + 1] if i + 1 < len(argv) else ""
            if not token.startswith("-"):
                return None
        return None
    if prog in _POWERSHELLS:
        for i, token in enumerate(argv[1:], start=1):
            name = token.lower().lstrip("-/")
            if not token.startswith(("-", "/")) or not name:
                continue
            if "encodedcommand".startswith(name) or name == "ec":
                return Decision(
                    "deny", "Encoded PowerShell commands cannot be inspected; not allowed."
                )
            if "command".startswith(name):
                return " ".join(argv[i + 1 :])
        return None
    if prog == "cmd":
        for i, token in enumerate(argv[1:], start=1):
            if token.lower() in {"/c", "/k"}:
                return " ".join(argv[i + 1 :])
        return None
    if prog in _EVALUATORS:
        return " ".join(argv[1:])
    return None


def _analyze(argv: list[str], raw: str) -> Decision | None:
    prog, args = _prog(argv[0]), argv[1:]
    if prog in {"export", "set", "setx"} and any(
        a.split("=", 1)[0].upper() in _BYPASS_ENV for a in args
    ):
        return Decision("deny", _BYPASS)
    if prog == "git":
        return _check_git(args, raw)
    if prog == "gh":
        return _check_gh(args)
    if prog in {"curl", "wget"} or prog in _PS_HTTP:
        return _check_http(prog, args)
    return None


def _git_parse(args: Sequence[str]) -> tuple[str | None, list[str], list[str]]:
    """Split git global options from the subcommand: (subcommand, rest, -c configs)."""
    configs: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        if token == "-c" and i + 1 < len(args):
            configs.append(args[i + 1])
            i += 2
        elif token in _GIT_VALUE_OPTS:
            i += 2
        elif token.startswith("-"):
            if token.startswith("-c") and len(token) > len("-c"):
                configs.append(token[2:])
            i += 1
        else:
            return token, list(args[i + 1 :]), configs
    return None, [], configs


def _check_git(args: Sequence[str], raw: str) -> Decision | None:  # noqa: PLR0911 (flat rule table)
    sub, rest, configs = _git_parse(args)
    if any(c.lower().startswith("core.hookspath") for c in configs):
        return Decision("deny", _BYPASS)
    if sub in {"push", "send-pack", "http-push"} or (sub == "lfs" and "push" in rest):
        return Decision("deny", _REMOTE)
    if sub == "remote":
        action = next((t for t in rest if not t.startswith("-")), None)
        if action in _REMOTE_WRITE_ACTIONS:
            return Decision("deny", "Repo policy: remotes are managed by the user, not Claude.")
        return None
    if sub == "config":
        return _check_git_config(rest)
    if sub == "commit":
        if _commit_skips_hooks(rest):
            return Decision("deny", _BYPASS)
        if _AI_MARKERS.search(raw):
            return Decision("deny", _ATTRIBUTION)
        return None
    if sub in {"merge", "rebase", "am", "cherry-pick", "revert", "pull"} and "--no-verify" in rest:
        return Decision("deny", _BYPASS)
    if sub == "reset" and "--hard" in rest:
        return Decision("ask", "`git reset --hard` discards work; confirm with the user.")
    if sub == "clean" and any(
        t == "--force" or re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", t) for t in rest
    ):
        return Decision("ask", "`git clean -f` deletes untracked files; confirm with the user.")
    return None


def _check_git_config(rest: Sequence[str]) -> Decision | None:
    if any(t in _GIT_CONFIG_READ_FLAGS for t in rest):
        return None
    key = next((t for t in rest if not t.startswith("-")), None)
    if key is not None and _GIT_PROTECTED_KEYS.match(key):
        return Decision(
            "deny", "Repo policy: git identity, aliases, remotes and hooksPath are user-managed."
        )
    return None


def _commit_skips_hooks(rest: Sequence[str]) -> bool:
    skip_next = False
    for token in rest:
        if skip_next:
            skip_next = False
            continue
        if token == "--":
            return False
        if token in _COMMIT_VALUE_OPTS:
            skip_next = True
        elif token == "--no-verify":
            return True
        elif re.fullmatch(r"-[A-Za-z]+", token):
            for flag in token[1:]:
                if flag == "n":
                    return True
                if flag in "mFCct":
                    break
    return False


def _check_gh(args: Sequence[str]) -> Decision | None:
    positional: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        if token in _GH_VALUE_OPTS:
            i += 2
            continue
        if not token.startswith("-"):
            positional.append(token)
            if len(positional) == _GH_GROUP_AND_ACTION or positional[0] == "api":
                break
        i += 1
    if not positional:
        return None
    group = positional[0]
    if group == "api":
        return Decision("deny", _REMOTE) if _gh_api_is_write(args[i + 1 :]) else None
    if group == "secret" and len(positional) > 1 and positional[1] != "list":
        return Decision("deny", _REMOTE)
    action = positional[1] if len(positional) > 1 else None
    if action is not None and action in _GH_WRITES.get(group, frozenset()):
        return Decision("deny", _REMOTE)
    return None


def _gh_api_is_write(rest: Sequence[str]) -> bool:
    method: str | None = None
    has_fields = False
    endpoint: str | None = None
    i = 0
    while i < len(rest):
        token = rest[i]
        if token in {"-X", "--method"} and i + 1 < len(rest):
            method = rest[i + 1].upper()
            i += 2
            continue
        if token.startswith("--method="):
            method = token.split("=", 1)[1].upper()
        elif token.startswith("-X") and len(token) > len("-X"):
            method = token[2:].upper()
        elif token in _GH_API_FIELD_OPTS:
            has_fields = True
            i += 2
            continue
        elif token.startswith(("--field=", "--raw-field=", "--input=")) or re.fullmatch(
            r"-[fF].+", token
        ):
            has_fields = True
        elif token in _GH_API_VALUE_OPTS:
            i += 2
            continue
        elif not token.startswith("-") and endpoint is None:
            endpoint = token
        i += 1
    if endpoint is not None and endpoint.strip("/").lower() == "graphql":
        return True
    if method is not None:
        return method not in {"GET", "HEAD"}
    return has_fields


def _check_http(prog: str, args: Sequence[str]) -> Decision | None:
    if not any(_GITHUB_HOST.search(a) for a in args):
        return None
    lowered = [a.lower() for a in args]
    if prog == "curl":
        write = _curl_is_write(args)
    elif prog == "wget":
        write = any(a.startswith(_WGET_DATA_OPTS) for a in lowered) or _method_is_write(
            lowered, "--method"
        )
    else:
        write = any(
            a.startswith(("-body", "-infile", "-form")) for a in lowered
        ) or _method_is_write(lowered, "-method")
    return Decision("deny", _REMOTE) if write else None


def _curl_is_write(args: Sequence[str]) -> bool:
    for i, token in enumerate(args):
        if token in {"-X", "--request"} and i + 1 < len(args):
            if args[i + 1].upper() not in {"GET", "HEAD"}:
                return True
        elif token.startswith("--request="):
            if token.split("=", 1)[1].upper() not in {"GET", "HEAD"}:
                return True
        elif token.startswith("-X") and len(token) > len("-X"):
            if token[2:].upper() not in {"GET", "HEAD"}:
                return True
        elif (
            token in _CURL_DATA_OPTS
            or token.startswith(("--data", "--json", "--form", "--upload-file"))
            or re.fullmatch(r"-d.+", token)
        ):
            return True
    return False


def _method_is_write(lowered: Sequence[str], flag: str) -> bool:
    for i, token in enumerate(lowered):
        value: str | None = None
        if token == flag and i + 1 < len(lowered):
            value = lowered[i + 1]
        elif token.startswith((flag + "=", flag + ":")):
            value = token[len(flag) + 1 :]
        if value is not None and value.strip("'\"").upper() not in {"GET", "HEAD"}:
            return True
    return False


def command_from(payload: JsonDict) -> str | None:
    """The shell command to inspect, or None when the payload isn't a shell tool call."""
    if payload.get("tool_name") not in {"Bash", "PowerShell"}:
        return None
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        raise TypeError("tool_input.command must be a string")
    return command


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    del argv  # no CLI options
    hook_io = HookIO.resolve(stdin, stdout, stderr, env)
    try:
        command = command_from(read_payload(hook_io.stdin))
        decision = evaluate(command) if command is not None else None
    except Exception as exc:  # fail closed: an uninspectable command is blocked
        hook_io.stderr.write(f"guard_bash: blocked; could not inspect the command ({exc!r}).\n")
        return 2
    if decision is not None:
        emit(hook_io.stdout, pretool_decision(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
