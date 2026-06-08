---
name: ai-agent-meeting-minutes
description: Create and publish W3C AI Agent Protocol CG meeting minutes for this repository from raw meeting notes. Use when the user invokes this project-local skill or asks to turn meeting notes into a meetings/YYYY-MM-DD.md document, draft mailing-list announcement text, and optionally commit and push the result to GitHub.
---

# AI Agent Protocol CG Meeting Minutes

## Scope

Use this skill only in the `ai-agent-protocol` repository. Convert raw AI Agent Protocol CG meeting notes into:

1. A Markdown minutes file under `meetings/YYYY-MM-DD.md`.
2. A mailing-list announcement text shown in the final response, not written to a file.
3. A git commit and push when the user requests publishing/submission.

Default to English for minutes and email text unless the user explicitly asks otherwise.

## Workflow

### 1. Inspect project context

- Work from the repository root.
- Read project notes if present (`claude.md`/`CLAUDE.md` and/or `codex.md`).
- Run `git status -sb` before editing.
- Read 2-3 recent files in `meetings/` to match the current house style, especially the newest `2026-*.md` files.

### 2. Determine the meeting date and filename

- Prefer an explicit date from the user's notes.
- If the user gives a relative date such as "last Wednesday", resolve it using the current date/timezone and use the exact ISO date.
- If the date cannot be determined safely, ask one concise question before writing.
- Write to `meetings/YYYY-MM-DD.md`.
- If the target file already exists, inspect it and update rather than overwriting blindly.

### 3. Write the minutes document

Use this structure unless nearby minutes show a stronger project convention:

```markdown
# Meeting Assets for AI Agent Protocol CG Meeting

**Date**: YYYY-MM-DD

## Quick Recap

...

## Agenda

1. ...

## Participants

- **Name** (Role if known)
- Other CG participants

## Discussion Topics

### I. Topic Title

...

## Next Steps

- **Name**: Action item.
- **Group members**: Action item.

## Notes

- Important links or clarifications.
```

Writing rules:

- Convert raw transcript/AI-summary text into durable minutes; do not paste noisy transcript artifacts.
- Preserve participant names, organizations, protocol names, and URLs from the input.
- Include the protocol draft URL when the protocol document is discussed: `https://w3c-cg.github.io/ai-agent-protocol/protocol.html`.
- Include the GitHub discussion URL when review/issues/PRs are discussed: `https://github.com/w3c-cg/ai-agent-protocol/`.
- Do not include Zoom task URLs unless the user explicitly asks.
- Use concise paragraphs and action-oriented next steps.
- When a service/protocol detail differs between user wording and the current repo document, prefer the current repo document and mention the exact names in Notes if useful.

### 4. Draft mailing-list announcement text

After writing the file, output an email-ready text in the final response. Do not save it to disk.

Use this format:

```text
Dear all,

Apologies for the slight delay in sharing the meeting summary.

The minutes from the AI Agent Protocol CG meeting held on Month D, YYYY, have now been compiled. Please review them at the link below and feel free to provide any feedback:

Meeting minutes: https://github.com/w3c-cg/ai-agent-protocol/blob/main/meetings/YYYY-MM-DD.md

This meeting focused on ...

[2-5 concise paragraphs summarizing main topics, collaboration points, protocol links, and next steps.]

We welcome any comments on the minutes or on the topics discussed.

Best regards,

Song and Gaowei
```

Include these links as separate lines when relevant:

```text
Protocol draft: https://w3c-cg.github.io/ai-agent-protocol/protocol.html
GitHub discussion: https://github.com/w3c-cg/ai-agent-protocol/
```

### 5. Validate

- Review the new file with `sed -n '1,260p' meetings/YYYY-MM-DD.md`.
- Run `git diff --check` before committing.
- Confirm `git status -sb` shows only intended changes, or ask the user before staging if unrelated files are present.

### 6. Commit and push when requested

If the user asks to submit, publish, push, or otherwise send changes to the cloud:

1. Stage only the intended minutes file unless the user explicitly includes other files.
2. Commit with `Add Month D meeting minutes`.
3. Push the current branch to `origin`.
4. Report the commit hash, branch, pushed remote, and changed file.

For this repository's usual flow, direct push to `main` is acceptable when already on `main` and the user asked to push. If on another branch, push that branch. Open a PR only if the user explicitly asks for a PR.
