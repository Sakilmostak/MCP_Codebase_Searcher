# MCP Codebase Searcher - Troubleshooting Guide

This document provides a comprehensive troubleshooting checklist for common issues encountered when setting up the `mcp-codebase-searcher` tool with Xyne, Claude Desktop, Cursor, or other AI clients.

## Root Cause Analysis
For a deep dive into historical issues regarding path resolution and logging, refer to [Issue #1: Working Directory Mismatch](https://github.com/Sakilmostak/MCP_Codebase_Searcher). The core issue historically is that MCP clients spawn servers with a working directory of `/` (root), breaking relative path access.

## Troubleshooting Checklist

### Symptom: "Not connected" Error
- [ ] Reload your editor/client window (e.g. `Cmd+Shift+P` → "Developer: Reload Window").
- [ ] Check if the MCP server process actually spawned via `ps aux | grep mcp-searcher-server`.
- [ ] Verify your config uses the exact, full absolute path to `uv` rather than just `"uv"`.
- [ ] Check your AI client's internal output panel for MCP connection errors.

### Symptom: The tool returns `[ { "error": "Security/Performance Error..." } ]`
The AI client passed a relative path (like `.`) to `paths`, while the MCP server's working directory was evaluated as `/`.  
**Fix:** Immediately instruct your AI to strictly use the **absolute path** to your workspace (e.g. `/Users/YourName/Code/Project`).

### Symptom: Empty Results (`[]`) or "0 accessible files found"
- [ ] Check your background telemetry logs by running `cat ~/.mcp_searcher.log`. This file natively tracks exactly what the scanner sees.
- [ ] Confirm if the directory path you/the LLM passed to `paths` actually exists.
- [ ] Your VS Code extension or AI client SDK may be failing to auto-index massive monorepos. Explicitly give the AI a subdirectory inside your project rather than the entire workspace.
- [ ] If using Windows, ensure paths are formatted correctly (e.g. `C:\\Users\\...` or `C:/Users/...`).

### Symptom: "spawn uv ENOENT" Error
Your AI Client does not share your terminal's `PATH`. A command of just `"command": "uv"` fails to start the server.
**Fix:** Use the full absolute path. Run `which uv` (macOS/Linux) or `where uv` (Windows) in your terminal and paste that exact string into your `"command"` configuration field.

### Symptom: API Keys not loading in `elaborate_finding`
- [ ] Verify you have a `.env` file in the directory where your Editor/Client opened the project workspace.
- [ ] Ensure you restarted the Editor/Client completely so the new `.env` triggers.
- [ ] Check the `~/.mcp_searcher.log` to see if LiteLLM threw an `AuthenticationError`.
