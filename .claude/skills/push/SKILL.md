---
name: push
description: Stage all changed files, generate a commit message from the diff, and push to GitHub. Use when the user says "push", "commit and push", "ship it", or asks to push changes to GitHub.
disable-model-invocation: true
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git diff:*), Bash(git commit:*), Bash(git push:*), Bash(git log:*)
---

## Context

- Current branch: !`git branch --show-current`
- Git status: !`git status`
- Staged and unstaged diff: !`git diff HEAD`
- Recent commits (for message style): !`git log --oneline -5`

## Your task

1. Stage all changed and untracked files with `git add` (be specific — avoid sensitive files like `.env`)
2. Write a concise commit message that follows the existing commit style shown above. Focus on *why*, not just *what*. Use a HEREDOC to pass the message.
3. Push the branch to origin with `git push` (use `-u origin <branch>` if the branch has no upstream yet)

Do all three steps in a single message. Do not explain your actions — just execute the tool calls.
