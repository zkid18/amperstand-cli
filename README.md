# amperstand

Thin HTTP client for an [amperstand-core](https://github.com/zkid18/ampersand-core) vault server. ~5 MB install, two runtime deps (`typer` + `httpx`), no extraction code — every command is a REST call to your server.

## Install

```bash
pip install amperstand
```

Requires Python 3.10+. You'll need an `amperstand-core` server running somewhere — see [ampersand-core](https://github.com/zkid18/ampersand-core).

## Connect to your server

```bash
# Save the API key to a 0600 file, export it from your shell rc
echo "<your-server-api-key>" > ~/.amperstand-api-key
chmod 600 ~/.amperstand-api-key
echo 'export AMPERSTAND_API_KEY="$(cat ~/.amperstand-api-key | tr -d "\n")"' >> ~/.zshrc
source ~/.zshrc

# Point the CLI at your server
amperstand vault backend set-server https://your-server \
    --api-key-env AMPERSTAND_API_KEY
```

⚠️ `--api-key-env AMPERSTAND_API_KEY` is the **name** of an env var, not the value. The CLI stores the name and reads the value at runtime — rotation stays cheap.

## Use

```bash
amperstand capture https://danluu.com/why-hardware-development-is-hard/
amperstand capture https://www.youtube.com/watch?v=e_NDFEWGW1w

amperstand feed add https://danluu.com/atom.xml
amperstand feed list
amperstand feed sync

amperstand vault status
```

Every command hits an endpoint on your server. Extraction, persistence, search — all server-side. The CLI just speaks HTTP.

## Documentation

Full docs live in the [amperstand-core repo's `docs/`](https://github.com/zkid18/ampersand-core/tree/main/docs) — Mintlify site. Run `mintlify dev` from that folder to preview. Key pages:

- **Install the CLI** — `cli-install.mdx`
- **Use the CLI** (the six things to know how to do day-to-day) — `cli-quickstart.mdx`
- **CLI reference** (every command, every flag) — `cli-reference.mdx`

## Local footprint

| File | Purpose |
| --- | --- |
| `~/.amperstand/config.json` | Server URL + the env-var name for your API key (mode 0600) |
| `~/.amperstand/amperstand.log` | CLI-side logs (HTTP requests, errors) |

That's it. No vault files on disk, no extraction state — the server owns all of it.

## License

MIT.
