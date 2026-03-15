import * as vscode from 'vscode';
import { AnalysisResult } from './api';

export function createWebviewPanel(result: AnalysisResult) {
    const panel = vscode.window.createWebviewPanel(
        'railDebugAnalysis',
        'Rail Debug Analysis',
        vscode.ViewColumn.One,
        {
            enableScripts: true,
        }
    );

    panel.webview.html = getWebviewContent(result);

    // Handle messages from webview
    panel.webview.onDidReceiveMessage(
        message => {
            if (message.command === 'copy') {
                vscode.env.clipboard.writeText(message.text);
                vscode.window.showInformationMessage('Copied to clipboard');
            }
        },
        undefined,
        []
    );
}

function getWebviewContent(result: AnalysisResult): string {
    return `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rail Debug Analysis</title>
    <style>
        body {
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            background-color: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
            margin: 0;
            padding: 20px;
        }
        .section {
            margin-bottom: 20px;
        }
        .section h2 {
            color: var(--vscode-textLink-foreground);
            border-bottom: 1px solid var(--vscode-panel-border);
            padding-bottom: 5px;
        }
        .code-snippet {
            background-color: var(--vscode-textCodeBlock-background);
            border: 1px solid var(--vscode-textBlockQuote-border);
            padding: 10px;
            margin: 10px 0;
            font-family: var(--vscode-editor-font-family);
            white-space: pre-wrap;
        }
        button {
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            padding: 5px 10px;
            cursor: pointer;
        }
        button:hover {
            background-color: var(--vscode-button-hoverBackground);
        }
    </style>
</head>
<body>
    <div class="section">
        <h2>Summary</h2>
        <p>${escapeHtml(result.summary)}</p>
    </div>
    <div class="section">
        <h2>Root Cause</h2>
        <p>${escapeHtml(result.root_cause)}</p>
    </div>
    <div class="section">
        <h2>Fix Suggestion</h2>
        <p>${escapeHtml(result.fix_suggestion)}</p>
    </div>
    <div class="section">
        <h2>Code Snippets</h2>
        ${result.code_snippets.map(snippet => `
            <div class="code-snippet">${escapeHtml(snippet)}</div>
            <button onclick="copyText('${escapeJs(snippet)}')">Copy</button>
        `).join('')}
    </div>
    <script>
        const vscode = acquireVsCodeApi();
        function copyText(text) {
            vscode.postMessage({ command: 'copy', text: text });
        }
    </script>
</body>
</html>`;
}

function escapeHtml(text: string): string {
    return text.replace(/[&<>"']/g, (match) => {
        const map: { [key: string]: string } = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return map[match];
    });
}

function escapeJs(text: string): string {
    return text.replace(/'/g, "\\'").replace(/\n/g, '\\n');
}