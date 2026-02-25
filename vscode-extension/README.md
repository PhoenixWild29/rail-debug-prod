# Rail Debug — VS Code Extension

AI-powered error analysis directly in your editor. Paste or select any error traceback and get instant diagnosis via the Quad-Tier Engine.

## Setup

1. **Start the Rail Debug server** in the repo root:
   ```bash
   python cli.py --serve --port 8000
   ```

2. **Install the extension** (once published, or install from VSIX):
   ```bash
   vsce package
   code --install-extension rail-debug-0.1.0.vsix
   ```

## Usage

1. Select an error traceback in any editor
2. Press `Cmd+Shift+D` (Mac) / `Ctrl+Shift+D` (Win/Linux)
   — or right-click → **Rail Debug: Analyze Error**
3. Results appear in the **Rail Debug** output panel

## Commands

| Command | Keybinding | Description |
|---------|-----------|-------------|
| Rail Debug: Analyze Error | `Cmd+Shift+D` | Tier 1–2 (fast, offline-first) |
| Rail Debug: Deep Analyze | — | Tier 4 (Claude Sonnet, full reasoning) |
| Rail Debug: Check Server Health | — | Verify server is reachable |

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `railDebug.serverUrl` | `http://localhost:8000` | Rail Debug API server URL |
| `railDebug.defaultMode` | `auto` | `auto` \| `haiku` \| `deep` |
| `railDebug.showStatusBar` | `true` | Show status bar button |
