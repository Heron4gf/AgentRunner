from __future__ import annotations

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Execute a shell command in the workspace. Use for running tests, "
                "linting, installing packages, git operations, and any other CLI tasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory relative to workspace root",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30)",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a new file. Fails if the file already exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Edit an existing file using the Morph applier model. "
                "Use '// ... existing code ...' to represent unchanged sections."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root",
                    },
                    "instruction": {
                        "type": "string",
                        "description": "Natural language description of the edit (first-person)",
                    },
                    "update": {
                        "type": "string",
                        "description": (
                            "Edit snippet using '// ... existing code ...' convention "
                            "for unchanged sections"
                        ),
                    },
                },
                "required": ["path", "instruction", "update"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file from the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": (
                "Search the codebase using regex patterns (ripgrep-compatible). "
                "Filter by file pattern (glob)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Regex pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in, relative to workspace root",
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": 'Glob pattern, e.g. "*.py"',
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum matches (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for current information via Tavily.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results (default: 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish_task",
            "description": "Signal task completion with a summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Task completion summary",
                    },
                },
                "required": [],
            },
        },
    },
]