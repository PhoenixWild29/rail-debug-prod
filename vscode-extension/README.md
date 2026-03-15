# Rail Debug — VS Code Extension

AI-powered error analysis directly in your editor. Select an error traceback and get instant diagnosis via the Rail Debug API.

## Setup

1. **Get an API key** from [debug.secureai.dev](https://debug.secureai.dev)
2. **Configure the extension**:
   - Open VS Code Settings
   - Set `railDebug.apiUrl` to `https://debug.secureai.dev` (or your server)
   - Set `railDebug.apiKey` to your API key

## Usage

1. Select an error traceback in any editor
2. Run **Rail Debug: Analyze Selection** from Command Palette
3. Results appear in a webview panel

## Commands

| Command | Description |
|---------|-------------|
| Rail Debug: Analyze Selection | Analyze selected text |
| Rail Debug: Analyze File | Analyze entire active file |

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `railDebug.apiUrl` | `https://debug.secureai.dev` | Rail Debug API server URL |
| `railDebug.apiKey` | — | Your API key |
