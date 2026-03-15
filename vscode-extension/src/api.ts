import { getApiUrl } from './config';

export interface AnalysisResult {
    summary: string;
    root_cause: string;
    fix_suggestion: string;
    code_snippets: string[];
    severity: string;
    confidence: number;
}

export async function analyzeSelection(errorText: string, apiKey: string): Promise<AnalysisResult> {
    const apiUrl = getApiUrl();
    const response = await fetch(`${apiUrl}/api/analyze`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-API-Key': apiKey,
        },
        body: JSON.stringify({
            traceback: errorText,
        }),
    });

    if (!response.ok) {
        throw new Error(`API request failed: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();
    return {
        summary: data.summary || 'No summary available',
        root_cause: data.root_cause || 'No root cause identified',
        fix_suggestion: data.fix_suggestion || 'No fix suggestion',
        code_snippets: data.code_snippets || [],
        severity: data.severity || 'unknown',
        confidence: data.confidence || 0,
    };
}