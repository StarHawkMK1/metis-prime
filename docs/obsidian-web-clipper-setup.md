# Obsidian Web Clipper — Setup Guide

This guide configures Obsidian Web Clipper to save clipped pages directly to
`raw/clips/` in your vault, satisfying Phase 6 AC2.

## Prerequisites

- Obsidian desktop app with your vault open
- [Obsidian Web Clipper](https://obsidian.md/clipper) browser extension installed

## Configuration

### Option A: Direct vault save (simplest)

1. Open the Obsidian Web Clipper extension settings.
2. Set **Save location** to your vault's `raw/clips/` directory.
   - Example: `~/second-brain-vault/raw/clips/`
3. Set **File name format** to `{date:YYYY-MM-DD}-{title:50}` to match vault naming conventions.
4. Ensure **Frontmatter** includes at minimum:
   ```yaml
   type: ref
   status: draft
   sources: [{url}]
   ```

After saving, clipped pages appear in `raw/clips/` and are picked up by
`second-brain ingest --inbox` (or the file watcher if you've configured `capture watch`
to monitor `raw/clips/`).

### Option B: POST to clipper endpoint

If you prefer routing clips through Metis Prime's own endpoint (useful for mobile
share-sheet integration):

1. Start the clipper server:
   ```
   second-brain capture serve
   ```
   Default: `http://127.0.0.1:7331`

2. In the Web Clipper extension, set **Webhook URL** to `http://127.0.0.1:7331/clip`.
3. Map the request body to:
   ```json
   { "content": "{content}", "url": "{url}", "title": "{title}" }
   ```

## Verification

After clipping a page, run:

```
second-brain status
```

You should see the inbox item count increase. Then run:

```
second-brain ingest --inbox
```

to process the clip into `wiki/`.

## Mobile share sheet (Option B only)

On Android/iOS, add a shortcut that sends a POST request to
`http://<your-PC-IP>:7331/clip` with the shared URL and page title.
Note: expose the server on your LAN only with `--host 0.0.0.0` and a firewall rule
limiting access to your devices. The default `127.0.0.1` binding is localhost-only.
