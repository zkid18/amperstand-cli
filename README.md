# Amperstand CLI

The command-line client for [Amperstand](https://github.com/zkid18/amperstand-core). It captures articles, YouTube videos, feeds, and newsletters into markdown files you own.

**This repo is deliberately thin.** All extraction and capture logic lives in [`amperstand-core`](https://github.com/zkid18/amperstand-core), which this package imports as a library — nothing is duplicated here. What this repo adds is the user-facing `amperstand` command plus the local-workflow glue core doesn't have: config, local state, an optional git-backed vault, and backend routing.

It is local-first. You can run it on any computer with Python and write output directly into a folder or Obsidian vault — commands run in-process against the core library, no server needed. Point it at a running [`amperstand-server`](https://github.com/zkid18/amperstand-core) instead and the same commands become thin HTTP calls.

## Install

```bash
git clone https://github.com/zkid18/amperstand-cli
cd amperstand-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
```

## Quick Start

Capture an article:

```bash
amperstand capture https://example.com/article
```

Print markdown to stdout instead of writing a file:

```bash
amperstand capture https://example.com/article --stdout
```

Capture into a specific folder:

```bash
amperstand capture https://example.com/article --output ~/notes/inbox
```

## What It Supports

- Articles and web pages
- YouTube videos and transcripts
- RSS and Atom feeds
- Newsletter emails and `.eml` files

## Common Commands

```bash
amperstand feed add https://example.com/feed.xml
amperstand feed sync --output ~/notes/inbox

amperstand email parse ./newsletter.eml --output ~/notes/inbox

amperstand config show
amperstand --version
```

## Local State

Amperstand stores local state in `~/.amperstand`, including:

- `state.json` for feed subscriptions and capture history
- `config.json` for settings
- `amperstand.log` for logs

## Notes

- Some JavaScript-heavy pages need Playwright. If Chromium has not been installed yet, run `playwright install chromium`.
- YouTube capture uses `yt-dlp`.
- Vault and git sync are optional. If you just want local files on another computer, you do not need the server at all.
