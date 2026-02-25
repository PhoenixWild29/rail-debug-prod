/**
 * Rail Debug VS Code Extension
 *
 * Sends selected error tracebacks to the Rail Debug API server and
 * displays AI analysis (severity, root cause, fix) in an output panel.
 *
 * Usage:
 *   1. Start the server: python cli.py --serve --port 8000
 *   2. Select a traceback in any editor
 *   3. Cmd+Shift+D  (or right-click → Rail Debug: Analyze Error)
 */

'use strict';

const vscode = require('vscode');
const https = require('https');
const http = require('http');
const { URL } = require('url');

let outputChannel;
let statusBarItem;

// ── Activation ────────────────────────────────────────────────────

function activate(context) {
    outputChannel = vscode.window.createOutputChannel('Rail Debug');

    context.subscriptions.push(
        vscode.commands.registerCommand('rail-debug.analyze', () => analyzeSelection(false)),
        vscode.commands.registerCommand('rail-debug.analyzeDeep', () => analyzeSelection(true)),
        vscode.commands.registerCommand('rail-debug.checkServer', checkServer),
    );

    const config = vscode.workspace.getConfiguration('railDebug');
    if (config.get('showStatusBar', true)) {
        statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
        statusBarItem.text = '$(search) Rail Debug';
        statusBarItem.command = 'rail-debug.analyze';
        statusBarItem.tooltip = 'Rail Debug: Analyze selected error (Cmd+Shift+D)';
        statusBarItem.show();
        context.subscriptions.push(statusBarItem);
    }

    // Update status bar visibility on config change
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(e => {
            if (e.affectsConfiguration('railDebug.showStatusBar') && statusBarItem) {
                const show = vscode.workspace.getConfiguration('railDebug').get('showStatusBar', true);
                show ? statusBarItem.show() : statusBarItem.hide();
            }
        })
    );
}

// ── Commands ──────────────────────────────────────────────────────

async function analyzeSelection(deep) {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showWarningMessage('Rail Debug: No active editor');
        return;
    }

    const selection = editor.selection;
    const traceback = editor.document.getText(selection.isEmpty ? undefined : selection).trim();

    if (!traceback) {
        vscode.window.showWarningMessage('Rail Debug: Select an error traceback first, then run this command');
        return;
    }

    const config = vscode.workspace.getConfiguration('railDebug');
    const serverUrl = config.get('serverUrl', 'http://localhost:8000');
    const mode = deep ? 'deep' : config.get('defaultMode', 'auto');

    await vscode.window.withProgress(
        {
            location: vscode.ProgressLocation.Notification,
            title: `Rail Debug: Analyzing (${mode} mode)…`,
            cancellable: false,
        },
        async () => {
            try {
                const result = await postJSON(`${serverUrl}/analyze`, {
                    traceback,
                    deep: mode === 'deep',
                    haiku: mode === 'haiku',
                    no_git: true,
                });
                showReport(result);
            } catch (err) {
                const msg = err.message || String(err);
                if (msg.includes('ECONNREFUSED') || msg.includes('ENOTFOUND')) {
                    const action = await vscode.window.showErrorMessage(
                        `Rail Debug: Cannot reach server at ${serverUrl}`,
                        'Start Server',
                    );
                    if (action === 'Start Server') {
                        showStartServerInstructions(serverUrl);
                    }
                } else {
                    vscode.window.showErrorMessage(`Rail Debug: ${msg}`);
                }
            }
        }
    );
}

async function checkServer() {
    const config = vscode.workspace.getConfiguration('railDebug');
    const serverUrl = config.get('serverUrl', 'http://localhost:8000');

    try {
        const result = await getJSON(`${serverUrl}/health`);
        vscode.window.showInformationMessage(
            `Rail Debug server OK — v${result.version} at ${serverUrl}`
        );
    } catch (err) {
        const action = await vscode.window.showErrorMessage(
            `Rail Debug: Server unreachable at ${serverUrl}`,
            'Show Setup',
        );
        if (action === 'Show Setup') {
            showStartServerInstructions(serverUrl);
        }
    }
}

// ── Output ────────────────────────────────────────────────────────

function showReport(report) {
    const { severity, tier, error_type, root_cause, suggested_fix, model, file_path, line_number } = report;

    const line = '═'.repeat(58);
    const dash = '─'.repeat(58);

    outputChannel.clear();
    outputChannel.appendLine(line);
    outputChannel.appendLine('  Rail Debug — AI Error Analysis');
    outputChannel.appendLine(line);
    outputChannel.appendLine(`  Severity:   ${(severity || 'unknown').toUpperCase()}`);
    outputChannel.appendLine(`  Tier:       ${tier} — ${tierLabel(tier)}${model ? ` (${model})` : ''}`);
    outputChannel.appendLine(`  Error:      ${error_type || 'unknown'}`);
    if (file_path) {
        outputChannel.appendLine(`  Location:   ${file_path}:${line_number || '?'}`);
    }
    outputChannel.appendLine(dash);
    outputChannel.appendLine(`  Root cause:`);
    outputChannel.appendLine(`    ${root_cause || '—'}`);
    outputChannel.appendLine('');
    outputChannel.appendLine(`  Suggested fix:`);
    outputChannel.appendLine(`    ${suggested_fix || '—'}`);
    outputChannel.appendLine(line);
    outputChannel.show(true);

    // Show inline notification with quick action
    const severityUpper = (severity || '').toUpperCase();
    const icon = { CRITICAL: '🔴', HIGH: '🟠', MEDIUM: '🟡', LOW: '🟢', INFO: '🔵' }[severityUpper] || '⚪';
    vscode.window.showInformationMessage(
        `${icon} Rail Debug [${severityUpper}]: ${root_cause || 'Analysis complete'}`,
        'Show Details'
    ).then(action => {
        if (action === 'Show Details') outputChannel.show(true);
    });
}

function showStartServerInstructions(serverUrl) {
    outputChannel.clear();
    outputChannel.appendLine('Rail Debug — Server Setup');
    outputChannel.appendLine('─'.repeat(40));
    outputChannel.appendLine('');
    outputChannel.appendLine('Start the Rail Debug server with:');
    outputChannel.appendLine('');
    outputChannel.appendLine('  python cli.py --serve --port 8000');
    outputChannel.appendLine('');
    outputChannel.appendLine(`Then ensure railDebug.serverUrl is set to: ${serverUrl}`);
    outputChannel.appendLine('(VS Code Settings → Extensions → Rail Debug)');
    outputChannel.show(true);
}

function tierLabel(tier) {
    return {
        1: 'Regex (offline)',
        2: 'Grok Fast',
        3: 'Claude Haiku 4.5',
        4: 'Claude Sonnet 4.6',
    }[tier] || 'Unknown';
}

// ── HTTP helpers ─────────────────────────────────────────────────

function postJSON(urlStr, body) {
    return new Promise((resolve, reject) => {
        let parsed;
        try { parsed = new URL(urlStr); } catch (e) { return reject(new Error(`Invalid URL: ${urlStr}`)); }

        const data = JSON.stringify(body);
        const options = {
            hostname: parsed.hostname,
            port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
            path: parsed.pathname + (parsed.search || ''),
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(data),
            },
        };

        const lib = parsed.protocol === 'https:' ? https : http;
        const req = lib.request(options, (res) => {
            let chunks = '';
            res.on('data', chunk => chunks += chunk);
            res.on('end', () => {
                try {
                    const json = JSON.parse(chunks);
                    if (res.statusCode >= 400) reject(new Error(json.detail || `HTTP ${res.statusCode}`));
                    else resolve(json);
                } catch (e) {
                    reject(new Error(`Non-JSON response (${res.statusCode}): ${chunks.slice(0, 120)}`));
                }
            });
        });
        req.on('error', reject);
        req.write(data);
        req.end();
    });
}

function getJSON(urlStr) {
    return new Promise((resolve, reject) => {
        let parsed;
        try { parsed = new URL(urlStr); } catch (e) { return reject(new Error(`Invalid URL: ${urlStr}`)); }

        const options = {
            hostname: parsed.hostname,
            port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
            path: parsed.pathname + (parsed.search || ''),
            method: 'GET',
        };

        const lib = parsed.protocol === 'https:' ? https : http;
        const req = lib.request(options, (res) => {
            let chunks = '';
            res.on('data', chunk => chunks += chunk);
            res.on('end', () => {
                try { resolve(JSON.parse(chunks)); }
                catch (e) { reject(new Error('Invalid JSON response')); }
            });
        });
        req.on('error', reject);
        req.end();
    });
}

// ── Deactivation ─────────────────────────────────────────────────

function deactivate() {
    if (outputChannel) outputChannel.dispose();
    if (statusBarItem) statusBarItem.dispose();
}

module.exports = { activate, deactivate };
