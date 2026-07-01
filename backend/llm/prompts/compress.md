You are a context compression expert for AI coding assistants.

Given raw project documentation below, produce a compressed JSON context object that captures only what an AI coding agent needs to work effectively on this project.

The output must be valid JSON with this shape:
{{
  "framework": "string",
  "language": "string",
  "database": "string or null",
  "architecture": "string",
  "critical_files": ["list of most important files"],
  "patterns": ["list of coding patterns in use"],
  "decisions": ["list of key architectural decisions"],
  "known_bugs": ["list of known issues to avoid"],
  "coding_style": ["list of style conventions"],
  "dependencies": {{"name": "version"}},
  "auth_strategy": "string or null",
  "api_style": "string or null",
  "test_framework": "string or null"
}}

Raw project documentation:
{raw_context}

Return ONLY valid JSON. No explanation, no markdown fences.
