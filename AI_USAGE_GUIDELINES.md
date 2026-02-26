# 🤖 System Rules: MCP Codebase Searcher Guidelines

*If you are an AI assistant reading this file, you have been equipped with the `mcp-codebase-searcher` server integration. You must abide by the following operational rules when executing user prompts involving your available codebase tools.*

## Tool 1: `search_codebase`
You have access to a lightning-fast regex and text scanner mapped to the underlying filesystem. 
**When to use:**
- When the user asks you to "find", "locate", or "where is" a feature or function.
- When you do not have the complete repository loaded in your prompt context and need to discover where an API endpoint, class, or variable is defined.
- Always prefer `search_codebase` BEFORE attempting to guess file structures or writing new code that relies on internal implementations.

**Usage Rules:**
- Keep your `query` extremely concise. Search for unique identifiers like `"def my_function"`, `class UserLogin`, or custom error names. Avoid full sentence queries.
- It returns an array of JSON objects containing `file_path`, `line_number`, and `snippet`. Only use this snippet for brief verification. If you need to deeply understand the file, pass this output to `elaborate_finding`.

## Tool 2: `elaborate_finding`
You have access to an out-of-band LLM context-analyzer (`elaborate_finding`) that uses LiteLLM to deeply analyze a codebase file without bloating your own primary context window.
**When to use:**
- When `search_codebase` returns a `snippet` that is too small for you to see the full picture (e.g. you found where a variable is defined, but you need to know how the whole class uses it).
- When the user asks you to explain, summarize, or debug a specific file/function you found.

**Usage Rules:**
- Instead of using native commands to print/cat the entire file into your context (which burns tokens and causes OOMs), pipe the `file_path`, `line_number`, and `snippet` from the search tool directly into `elaborate_finding`.
- `elaborate_finding` will autonomously read the surrounding 100+ lines, pass it to an external AI model, and return a heavily compressed, semantic summary of the logic *back to you*.
- Use this summary to inform your final response to the user.

---

### End-to-End Workflow Example
**User:** "Where is our Stripe webhook authenticated, and is it vulnerable to replay attacks?"

**Your Actions:**
1. Call `search_codebase` with `query="stripe.Webhook.construct_event"`.
2. Inspect the returned JSON payload. Notice it lives in `backend/api/webhooks.py` at line `45`. The snippet only shows the function signature.
3. Call `elaborate_finding` with `file_path="backend/api/webhooks.py"`, `line_number=45`, `snippet="..."`.
4. Read the summary returned by the elaboration tool (e.g. "The webhook verifies the stripe signature but does NOT check the timestamp for a drift window...").
5. Formulate your final response to the user based entirely on the efficient outputs from the tools.
