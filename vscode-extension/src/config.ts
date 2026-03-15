import * as vscode from 'vscode';

export function getApiUrl(): string {
    return vscode.workspace.getConfiguration('railDebug').get('apiUrl', 'https://debug.secureai.dev');
}

export function getApiKey(): string | undefined {
    return vscode.workspace.getConfiguration('railDebug').get('apiKey');
}