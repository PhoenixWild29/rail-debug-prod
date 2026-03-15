import * as vscode from 'vscode';
import { analyzeSelection } from './api';
import { createWebviewPanel } from './webview';
import { getApiUrl, getApiKey } from './config';

let statusBarItem: vscode.StatusBarItem;
let outputChannel: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext) {
    outputChannel = vscode.window.createOutputChannel('Rail Debug');
    context.subscriptions.push(outputChannel);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('rail-debug.analyzeSelection', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showErrorMessage('No active editor');
                return;
            }
            const selection = editor.selection;
            const text = editor.document.getText(selection);
            if (!text) {
                vscode.window.showErrorMessage('No text selected');
                return;
            }
            await analyzeAndShow(text);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('rail-debug.analyzeFile', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showErrorMessage('No active editor');
                return;
            }
            const text = editor.document.getText();
            await analyzeAndShow(text);
        })
    );

    // Status bar
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'rail-debug.analyzeSelection';
    statusBarItem.text = '$(bug) Rail Debug';
    statusBarItem.tooltip = 'Click to analyze selected error';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);
}

async function analyzeAndShow(errorText: string) {
    const apiKey = getApiKey();
    if (!apiKey) {
        const result = await vscode.window.showInformationMessage(
            'API key not set. Configure railDebug.apiKey in settings.',
            'Open Settings'
        );
        if (result === 'Open Settings') {
            vscode.commands.executeCommand('workbench.action.openSettings', 'railDebug');
        }
        return;
    }

    outputChannel.appendLine('Analyzing error...');
    try {
        const result = await analyzeSelection(errorText, apiKey);
        createWebviewPanel(result);
    } catch (error) {
        outputChannel.appendLine(`Error: ${error}`);
        vscode.window.showErrorMessage(`Analysis failed: ${error}`);
    }
}

export function deactivate() {}