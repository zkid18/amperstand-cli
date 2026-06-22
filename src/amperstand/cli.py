"""CLI entry point for Amperstand — HTTP-only client for an amperstand-core server."""

from __future__ import annotations

import json

import typer

from amperstand import __version__
from amperstand.client import Client, ClientError
from amperstand.config import (
    clear_backend_config,
    load_backend_config,
    load_config,
    save_backend_config,
    set_value,
)
from amperstand.log_setup import setup_logging

app = typer.Typer(
    name="amperstand",
    help="HTTP client for an amperstand-core vault server. Capture, search, manage feeds.",
    add_completion=False,
)

feed_app = typer.Typer(help="Manage RSS/Atom feed subscriptions on the server.")
app.add_typer(feed_app, name="feed")

vault_app = typer.Typer(help="Backend config + health check.")
app.add_typer(vault_app, name="vault")

config_app = typer.Typer(help="View and update local CLI configuration.")
app.add_typer(config_app, name="config")


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"amperstand {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Amperstand — HTTP client for an amperstand-core vault server."""
    setup_logging()


# ── Client construction ───────────────────────────────────────────────

def _client() -> Client:
    """Construct an HTTP client from the saved backend config.

    Errors out with a clear hint if no backend is set — the CLI does
    nothing useful without a server to talk to.
    """
    cfg = load_backend_config()
    if not cfg or cfg.get("kind") != "http":
        typer.echo(
            "No server configured. Run:\n"
            "  amperstand vault backend set-http <url> --api-key-env AMPERSTAND_API_KEY",
            err=True,
        )
        raise typer.Exit(code=1)
    http = cfg.get("http") or {}
    try:
        return Client(
            base_url=http["url"],
            api_key=http.get("api_key"),
            api_key_env=http.get("api_key_env"),
        )
    except (ClientError, KeyError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


def _bail(msg: str, code: int = 1) -> None:
    typer.echo(f"Error: {msg}", err=True)
    raise typer.Exit(code=code)


# ── Capture ───────────────────────────────────────────────────────────


@app.command()
def capture(
    url: str = typer.Argument(help="URL to capture."),
    no_persist: bool = typer.Option(
        False,
        "--no-persist",
        help="Extract on the server but don't save to the vault.",
    ),
) -> None:
    """Send a URL to the server for capture. Server extracts + persists."""
    with _client() as c:
        try:
            doc = c.capture(url, persist=not no_persist)
        except ClientError as e:
            _bail(str(e))
    title = doc.get("title") or url
    doc_id = doc.get("id")
    path = doc.get("path")
    if doc_id:
        typer.echo(f"Saved: {doc_id} — {title}")
        if path:
            typer.echo(f"  {path}")
    else:
        typer.echo(f"Extracted (not persisted): {title}")


# ── Feeds ─────────────────────────────────────────────────────────────


@feed_app.command("add")
def feed_add(
    url: str = typer.Argument(help="RSS/Atom feed URL."),
    name: str | None = typer.Option(None, "--name", "-n", help="Display name for the feed."),
    tags: list[str] = typer.Option([], "--tag", "-t", help="Tags for this feed (repeatable)."),
) -> None:
    """Subscribe the server to an RSS/Atom feed."""
    with _client() as c:
        try:
            row = c.feeds_register(url, name=name, tags=tags)
        except ClientError as e:
            _bail(str(e))
    label = row.get("label") or row.get("name") or url
    typer.echo(f"Subscribed: {label}")


@feed_app.command("remove")
def feed_remove(
    target: str = typer.Argument(
        help="Feed ID or URL. URL is matched against the server's list."
    ),
) -> None:
    """Unsubscribe by feed ID or URL."""
    with _client() as c:
        try:
            items = c.feeds_list()
        except ClientError as e:
            _bail(str(e))
        feed_id = None
        for it in items:
            if it.get("feed_id") == target or it.get("url") == target:
                feed_id = it.get("feed_id")
                break
        if feed_id is None:
            _bail(f"not subscribed: {target}")
        try:
            c.feeds_remove(feed_id)
        except ClientError as e:
            _bail(str(e))
    typer.echo(f"Removed: {target}")


@feed_app.command("list")
def feed_list() -> None:
    """List subscribed feeds on the server."""
    with _client() as c:
        try:
            items = c.feeds_list()
        except ClientError as e:
            _bail(str(e))
    if not items:
        typer.echo("No feeds subscribed. Use 'amperstand feed add <url>' to add one.")
        return
    for it in items:
        label = it.get("label") or it.get("name") or it.get("url")
        tags = it.get("tags") or []
        tag_str = f"  [{', '.join(tags)}]" if tags else ""
        disabled = "" if it.get("enabled", True) else "  (disabled)"
        typer.echo(f"  {label}{tag_str}{disabled}")
        typer.echo(f"    {it.get('url')}")
        last = it.get("last_sync") or it.get("last_sync_at")
        if last:
            typer.echo(f"    last sync: {last} ({it.get('last_status') or '?'})")


@feed_app.command("sync")
def feed_sync() -> None:
    """Trigger a server-side sync across all enabled feeds."""
    with _client() as c:
        try:
            result = c.feeds_sync()
        except ClientError as e:
            _bail(str(e))
    feeds = result.get("feeds_synced", result.get("total_feeds", 0))
    new = result.get("new_items", 0)
    errors = result.get("errors") or []
    typer.echo(f"Synced {feeds} feed(s), {new} new item(s).")
    for err in errors:
        typer.echo(f"  error: {err}", err=True)


# ── Vault (health + backend config) ──────────────────────────────────


@vault_app.command("status")
def vault_status() -> None:
    """Show server health + total doc count."""
    with _client() as c:
        try:
            h = c.health()
            count = c.docs_count()
        except ClientError as e:
            _bail(str(e))
    typer.echo(f"Server: {h.get('status', 'unknown')}")
    typer.echo(f"Docs: {count}")


@app.command(name="rotate-key")
def rotate_key(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt.",
    ),
) -> None:
    """Mint a new API key on the server and update your local key file.

    What happens:

    1. Server mints a new 64-char hex key, writes it to /etc/amperstand/env,
       updates its own in-memory key. The next request requires the new key.
    2. CLI updates ~/.amperstand-api-key with the new value (mode 0600).
    3. You re-source your shell rc (`source ~/.zshrc`) for new shells to pick
       it up.
    4. SSH in and restart the bot / vault-watcher / feed-sync, which still
       hold the OLD key in their process memory.

    Trade-off: this command requires the EXISTING API key to authenticate.
    A leaked key can rotate itself — locking you out. Recovery is SSH-only:
    `amperstand-admin rotate-key` on the server. Most operators are fine with
    this; if you're rotating because the key leaked, also revoke any sessions
    you can't track.
    """
    import os as _os
    import sys as _sys
    from pathlib import Path as _Path

    if not yes:
        # Refuse non-interactive runs without --yes rather than crashing in
        # typer.confirm with an opaque Abort exception. CI / cron / systemd
        # all run with stdin not a TTY.
        if not _sys.stdin.isatty():
            _bail(
                "non-interactive shell (stdin not a TTY). Pass --yes to confirm."
            )
        typer.echo(
            "About to mint a new API key on the server and replace ~/.amperstand-api-key.\n"
            "Old key will stop being accepted by the server immediately (~25s drain window).\n"
            "Telegram bot / extension / other clients need their own restart / re-paste."
        )
        if not typer.confirm("Continue?"):
            raise typer.Exit(code=1)

    with _client() as c:
        try:
            resp = c.rotate_api_key()
        except ClientError as e:
            _bail(str(e))

    new_key = resp.get("new_api_key")
    if not new_key:
        _bail("server didn't return a new key")

    typer.echo("")
    typer.echo(f"New API key: {new_key}")
    typer.echo("")

    # Symlink-safe atomic write of the local key file.
    # - O_NOFOLLOW: if ~/.amperstand-api-key is a pre-planted symlink, refuse
    #   to follow (we'd otherwise write the new key into the symlink's target,
    #   possibly an attacker-controlled location).
    # - mode 0o600 set at create time, NOT after — no TOCTOU window where the
    #   file briefly exists with umask-default perms (typically 0o644) holding
    #   the new key.
    key_file = _Path.home() / ".amperstand-api-key"
    try:
        flags = _os.O_WRONLY | _os.O_CREAT | _os.O_TRUNC | _os.O_NOFOLLOW
        fd = _os.open(str(key_file), flags, 0o600)
        try:
            with _os.fdopen(fd, "w") as f:
                f.write(new_key + "\n")
        except Exception:
            _os.close(fd)
            raise
        # Defense in depth: re-chmod in case the file pre-existed at a wider
        # mode (O_CREAT's mode arg only applies when creating; if the file
        # already existed, its existing mode is preserved by O_TRUNC).
        _os.chmod(str(key_file), 0o600)
        typer.echo(f"Updated {key_file} (mode 0600).")
    except OSError as e:
        # ELOOP from O_NOFOLLOW means it's a symlink — call that out
        # specifically so the user understands why we refused.
        import errno as _errno

        if isinstance(e, OSError) and e.errno in (_errno.ELOOP, _errno.EMLINK):
            typer.echo(
                f"Refused to write {key_file}: it's a symlink.\n"
                f"Symlinks here are a security risk — remove it and re-run:\n"
                f"  rm {key_file} && amperstand rotate-key --yes\n"
                f"In the meantime, paste this key manually into a fresh file:\n"
                f"  echo '{new_key}' > {key_file} && chmod 600 {key_file}",
                err=True,
            )
        else:
            typer.echo(
                f"Could not update {key_file}: {e}\n"
                f"Save the key above into that file manually.",
                err=True,
            )

    warning = resp.get("warning")
    if warning:
        typer.echo("")
        typer.echo(warning)

    typer.echo("")
    typer.echo("Run `source ~/.zshrc` (or open a new terminal) for new shells to pick up the value.")


backend_app = typer.Typer(help="Configure the server URL + API key.")
vault_app.add_typer(backend_app, name="backend")


@backend_app.command("show")
def backend_show(
    show_secret: bool = typer.Option(
        False,
        "--show-secret",
        help="Print the api_key value in plaintext. Default: redacted.",
    ),
) -> None:
    """Show the configured server URL + API key resolution mode.

    By default any stored api_key VALUE is redacted in the output, since
    operators commonly run this when debugging auth failures (screen-share,
    paste into a GitHub issue). Pass --show-secret to print the literal.
    """
    cfg = load_backend_config()
    if not cfg:
        typer.echo("No backend configured.")
        raise typer.Exit(code=1)
    redacted = _redact_backend_config(cfg) if not show_secret else cfg
    typer.echo(json.dumps(redacted, indent=2))


def _redact_backend_config(cfg: dict) -> dict:
    """Return a copy with `http.api_key` masked. Does not touch api_key_env (just a name)."""
    import copy

    safe = copy.deepcopy(cfg)
    http = safe.get("http")
    if isinstance(http, dict) and "api_key" in http:
        val = http["api_key"]
        # Show first 4 + last 4 chars; mask the rest. Empty/short → fully masked.
        if isinstance(val, str) and len(val) >= 12:
            http["api_key"] = f"{val[:4]}…{val[-4:]} (redacted; pass --show-secret to reveal)"
        else:
            http["api_key"] = "(redacted; pass --show-secret to reveal)"
    return safe


@backend_app.command("set-http")
def backend_set_http(
    url: str = typer.Argument(help="Server URL, e.g. http://your-server:8765"),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help="Bearer token value. Prefer --api-key-env — passing the value here writes it to ~/.amperstand/config.json.",
    ),
    api_key_env: str | None = typer.Option(
        None,
        "--api-key-env",
        help="Name of the env var holding the bearer token (e.g. AMPERSTAND_API_KEY).",
    ),
) -> None:
    """Point the CLI at an amperstand-core server."""
    if not api_key and not api_key_env:
        _bail("Provide either --api-key or --api-key-env (recommended).")
    cfg: dict = {"kind": "http", "http": {"url": url.rstrip("/")}}
    if api_key:
        # Loud warning: --api-key VALUE writes the secret to ~/.amperstand/config.json
        # AND lands the full command line in shell history + ps aux argv during
        # this command's lifetime. We accept it (some users genuinely don't have
        # env vars wired) but make the cost explicit.
        typer.echo(
            "WARNING: --api-key wrote the secret to ~/.amperstand/config.json AND\n"
            "         to your shell history (~/.zsh_history / ~/.bash_history).\n"
            "         Prefer:  --api-key-env AMPERSTAND_API_KEY\n"
            "         and:     export AMPERSTAND_API_KEY=<value> (in your shell rc)\n"
            "         If this is a long-lived host, rotate the key after this session.",
            err=True,
        )
        cfg["http"]["api_key"] = api_key
    if api_key_env:
        cfg["http"]["api_key_env"] = api_key_env
    save_backend_config(cfg)
    typer.echo(f"Backend set: {url}")


@backend_app.command("clear")
def backend_clear() -> None:
    """Forget the configured server."""
    clear_backend_config()
    typer.echo("Backend cleared.")


# ── Config ────────────────────────────────────────────────────────────


@config_app.command("show")
def config_show() -> None:
    """Print local CLI configuration as JSON."""
    typer.echo(json.dumps(load_config(), indent=2))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="Dotted config key (e.g. logging.level)."),
    value: str = typer.Argument(help="Value to set."),
) -> None:
    """Set a configuration value (e.g. amperstand config set logging.level DEBUG)."""
    try:
        set_value(key, value)
    except ValueError as exc:
        _bail(str(exc))
    typer.echo(f"Set {key} = {value}")
