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


backend_app = typer.Typer(help="Configure the server URL + API key.")
vault_app.add_typer(backend_app, name="backend")


@backend_app.command("show")
def backend_show() -> None:
    """Show the configured server URL + API key resolution mode."""
    cfg = load_backend_config()
    if not cfg:
        typer.echo("No backend configured.")
        raise typer.Exit(code=1)
    typer.echo(json.dumps(cfg, indent=2))


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
