import hashlib
import re
import os
from typing import Tuple

def normalize_traceback(tb: str) -> Tuple[str, str]:
    &quot;&quot;&quot;
    Normalize traceback: extract filename:line, collapse duplicates, return (sha256_hash, snippet[:500])
    &quot;&quot;&quot;
    lines = tb.strip().splitlines()
    normalized_lines = []
    seen = set()
    
    for line in lines:
        # Match Python traceback: File &quot;path&quot;, line N,
        match = re.search(r'File &quot;([^&quot;]+)&quot;, line (\d+),', line)
        if match:
            filename = os.path.basename(match.group(1))
            lineno = match.group(2)
            key = f&quot;{filename}:{lineno}&quot;
            if key not in seen:
                seen.add(key)
                normalized_lines.append(key)
        # Fallback: any file:line
        match_fb = re.search(r'([a-zA-Z0-9_.-]+):(\d+)', line)
        if match_fb and match_fb.group(1) not in seen:
            key = f&quot;{match_fb.group(1)}:{match_fb.group(2)}&quot;
            if key not in seen:
                seen.add(key)
                normalized_lines.append(key)
    
    norm_tb = '\n'.join(normalized_lines)
    tb_hash = hashlib.sha256(norm_tb.encode('utf-8')).hexdigest()
    tb_snippet = norm_tb[:500]
    
    return tb_hash, tb_snippet
