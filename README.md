# VerbatimCV MCP server

<!-- mcp-name: io.github.VerbatimCV/verbatimcv -->

Give your AI agent one tool, `parse_resume`, that turns a CV or resume (PDF or DOCX) into verified,
versioned JSON: candidate details, experience with dates, education, skills, languages, and the
candidate's stated preferences (work arrangement, availability, compensation, location, work
authorisation).

- **Every field is quoted from the CV.** Each preference comes with `source` (stated, inferred or
  absent), a confidence and the verbatim quote it came from. Nothing is invented; missing facts are null.
- **Dates are parsed by code**, not guessed, with warnings for year-only or ambiguous dates.
- **Safe to automate.** Hidden text and prompt-injection attempts in the CV are removed and reported.
  Protected characteristics (age, date of birth, gender, marital status, nationality, photo) are never
  returned. `agent_guidance.confirm_before_acting` lists what to check with a human first.

## Set up in Claude Desktop

1. Get a free API key at https://api.verbatimcv.com/account?ref=mcp (50 parses a month, no card). It starts with `vcv_`.
2. Open Claude Desktop → Settings → Developer → Edit Config, and add this inside `"mcpServers"`:

```json
"verbatimcv": {
  "command": "uvx",
  "args": ["verbatimcv-mcp"],
  "env": { "VERBATIMCV_API_KEY": "vcv_your_key_here" }
}
```

3. Restart Claude Desktop. If it can't find `uvx`, use its full path (run `which uvx`), for example
   `/opt/homebrew/bin/uvx` on a Mac with Homebrew.

Any MCP client that runs stdio servers works the same way: run `uvx verbatimcv-mcp` with
`VERBATIMCV_API_KEY` set.

## Using it

Ask your agent something like "Parse the CV at ~/Downloads/jane-doe-cv.pdf and tell me if she's open to
remote contract work." The tool takes exactly one of:

- `file_path`: a PDF or DOCX on your computer (up to 10 MB). Files dragged into a chat window usually
  have no path the server can read; save the file and give its path instead.
- `url`: a public `https://` link to a PDF or DOCX.

The CV is sent to the VerbatimCV API for processing and is not stored.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `VERBATIMCV_API_KEY` | (required) | Your API key. |
| `VERBATIMCV_API_URL` | `https://api.verbatimcv.com` | API base URL. Must be `https://`. |
