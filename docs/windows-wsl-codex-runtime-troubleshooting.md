# Windows WSL Codex Runtime Troubleshooting

Status: added for `AGENT-1045`.

Use this guide when Codex, Docker, Python, or the durable limit guard reports an
unavailable runtime even though credentials and Jira/GitHub access look correct.
The most common failure is a Windows/WSL path boundary where Codex opens the
repository through a UNC path such as `\\wsl.localhost\Ubuntu\...` and the local
execution helper fails before a shell can start.

## Symptoms

Treat these as path/setup blockers before blaming Jira, GitHub, or Codex quota:

1. Codex shell cannot start and reports `helper_unknown_error: setup refresh had errors`.
2. `python` is not found, or `python3` points to an unsupported interpreter.
3. `agentic codex-limits latest` reports missing or stale records because the
   command is reading a different durable root than the Docker/API process.
4. The PO inbox UI/API sees one `data/po-inbox` location while a worker or
   session writes another.
5. Git status, branch, or pull request links do not match the expected target
   repository.

## Safe Windows Alias Workaround

The Product Owner validated this workaround during Release 1.2 Sprint 8:

1. Leave the real repository exactly where it is.
2. Create a Windows directory alias to that repository. Prefer a directory
   junction when Windows accepts the target; use a directory symbolic link when
   the target is a WSL UNC path and junction creation is rejected.
3. Open the alias path in Codex instead of the original UNC path.
4. Verify Git resolves back to the canonical repository.
5. Continue development through the alias path.

Example commands from an elevated Windows terminal, adjusted to the local paths:

```bat
mkdir C:\agentic-links
mklink /J C:\agentic-links\agentic-bolierplate \\wsl.localhost\Ubuntu\home\filip\business\agentic-bolierplate
```

If `/J` cannot target the UNC path on the machine, use a directory symbolic link
instead:

```powershell
New-Item -ItemType SymbolicLink `
  -Path C:\agentic-links\agentic-bolierplate `
  -Target \\wsl.localhost\Ubuntu\home\filip\business\agentic-bolierplate
```

The alias is only a local operator path. Do not commit it, place durable project
data inside it separately, or copy credentials into it.

## Canonical Repository Check

Run these checks from the alias path before starting a live runtime proof or a
worker stage:

```bash
git rev-parse --show-toplevel
git remote -v
git status --short
```

Expected result:

1. The top-level path points to the real repository checkout, not a new copied
   folder with unrelated Git metadata.
2. The remote is the intended repository.
3. There are no unrelated uncommitted changes before the sprint starts.

If Git resolves to a different checkout, stop and fix the alias or open the
correct project in Codex.

## Python And Agentic CLI Check

The project requires Python 3.11 or newer for current runtime modules. Validate
which executable the session uses:

```bash
python --version
python3 --version
python -m pip --version
```

When the package is not installed, run source commands with `PYTHONPATH=src`:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli --help
PYTHONPATH=src python -m agentic_boilerplate.cli setup validate --project-root . --codex-limits-root data/codex-limits
```

If `python` is missing but `python3` exists, either install/configure the
expected Python version or use `python3` only when it is 3.11+. Do not treat a
Python path failure as a Codex quota failure.

## Durable Limit And Inbox Path Check

The host session, Docker API, operator UI, and workers must agree on the same
durable roots. Validate the configured roots before a worker spends Codex quota:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli codex-limits latest --json --codex-limits-root data/codex-limits
PYTHONPATH=src python -m agentic_boilerplate.cli po-inbox list --status open
```

For Docker, the default mount is:

```text
./data:/workspace/data
```

The operator API command reads:

```text
agentic --inbox-root /workspace/data/po-inbox api serve --data-root /workspace/data --host 0.0.0.0 --port 8000
```

If a worker reads `data/codex-limits` from a different checkout or mounted path,
the guard can falsely report no available limit record. Fix the path and rerun
the setup validation before resuming.

## Worker Action

When any of these checks fail, the worker or session must:

1. Stop before claiming new Jira work or issuing a Codex request.
2. Record a startup/path diagnostic with secrets redacted.
3. Create or update a PO inbox blocker if operator action is required.
4. Resume only after the alias, Python executable, durable path, Git remote, and
   Codex limit record all pass validation.

This troubleshooting path unblocks setup and evidence collection. It does not
by itself prove `AGENT-967`; the live proof still requires a successful
host-side run and a passing `UnattendedRuntimeProofReport`.
