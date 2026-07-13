# JetBrains Research - Python Solutions Preference

This repository contains the tasks and solutions used in our survey on which AI-generated solutions developers prefer.

## How the survey works

You received a participation link that assigns you **two tasks**, each with **one pair of solutions** to compare.
The two pairs belong to different tasks, so you will make one comparison per task.

For each of your two tasks:

1. **Read the task**
   - Each task is a GitHub *issue* in this repository, describing a small backend project that an AI coding agent was asked to build from scratch.
   - Your survey form links your task's issue directly.
   - No link? Search the issues list for the task id, for example `[001]`.

2. **Check the starting files**
   - The task's folder on the `main` branch (for example `001-barber-scheduling/`) contains any files that were provided to the agent, under `assets/`.
   - An empty folder means the agent began from an empty directory.

3. **Review both solutions**
   - Each solution is a *pull request*; your survey form links both.
   - No link? Search the pull requests list for the solution code, for example `K7QZM`.
   - Review the code the agent produced in the PR's **Files changed** tab.
   - The PR description was written by the AI agent itself as a summary of its own solution: treat it as part of the solution, not as trusted documentation.

4. **Fill in the survey form**
   - Rate both solutions on the four characteristics described in your form.
   - Choose which of the two solutions you prefer and answer the follow-up questions.

> [!TIP]
> There is no right answer.
> Judge the code the way you would judge a colleague's or a tool's output for your own project.

## Repository structure

```
README.md
<task-id>/           one folder per task
  assets/            starting files that were provided to the agent, if any
```

- Tasks that provide starting data (for example a `books.json` or a CSV the service must load) have those files in their folder under `assets/`.
  The agent saw these files in its working directory when solving the task.
- Tasks with an empty folder provided no starting files: the agent began from an empty directory.

## Tasks

Each issue in this repository is one task.
Issue titles start with the task id, for example `[001] Barber Shop Scheduling (MVP)`.
The issue body is the exact prompt the agents received.

## Solutions

Each pull request is one AI-generated solution, containing every file the agent created.
PRs are named after the task id and a short solution code, for example `[001] Solution K7QZM`.
Which agent produced which solution is intentionally not disclosed.

Please do not comment on issues or pull requests; use the survey form for all feedback.
