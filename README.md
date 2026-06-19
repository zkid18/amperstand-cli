# Amperstand CLI

Thin HTTP client for an [`amperstand-core`](https://github.com/zkid18/ampersand-core) server. Capture URLs, YouTube videos, RSS feeds, and newsletter `.eml` files into your remote vault from the terminal.

The CLI does **no extraction itself** — every command translates to a REST call against your Amperstand server. Lightweight install (no Playwright, no yt-dlp, no heavy ML deps), small footprint.

📖 **Docs** — full reference at [zkid18/ampersand-core/docs/](https://github.com/zkid18/ampersand-core/tree/main/docs).

## Install

```bash
pip install amperstand
```

You'll need an `amperstand-core` server running somewhere. See [zkid18/ampersand-core](https://github.com/zkid18/ampersand-core) to set one up — typically on a $4 droplet.

## Setup

Two env vars + one config command:

```bash
# The bearer token your server is using
export AMPERSTAND_API_KEY="<the-64-char-hex-from-your-server>"

# Point the CLI at your server (use --api-key-env to pass the env var NAME, not the value)
amperstand vault backend set-http http://your-server:8765 \
    --api-key-env AMPERSTAND_API_KEY
```

> ⚠️ Pass `--api-key-env AMPERSTAND_API_KEY` (the name), not the key value itself. The CLI stores the name in `~/.amperstand/config.json` and reads the value at runtime — rotating the key is just `export AMPERSTAND_API_KEY=<new>`.

To make this survive new shells, add the export to `~/.zshrc`.

## Use

```bash
amperstand capture https://danluu.com/why-hardware-development-is-hard/
amperstand capture https://www.youtube.com/watch?v=e_NDFEWGW1w

amperstand feed add https://danluu.com/atom.xml
amperstand feed list
amperstand feed sync

amperstand vault status
amperstand config show
```

Every command hits an endpoint on your server. Extraction, persistence, search — all run server-side. The CLI just speaks HTTP.

## Configuration

| File | Purpose |
| --- | --- |
| `~/.amperstand/config.json` | Server URL + the env-var name for your API key |
| `~/.amperstand/amperstand.log` | CLI-side logs (HTTP requests, errors) |

That's the entire local footprint. No vault files on disk, no extraction state — the server owns all of it.

## License

MIT.
