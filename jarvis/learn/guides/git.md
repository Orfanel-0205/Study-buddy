---
title: Git: daily workflow, branches and team habits
summary: Git from the DevNet basics (three states, local vs remote) to how teams actually work - branches, commit messages, pull requests, merge conflicts, undoing mistakes and keeping secrets out.
tags: git, github, version control, branches, commits, pull request, merge, rebase, conflicts, devnet
order: 3
---

# Git: daily workflow, branches and team habits

## The basics (DevNet Module 3.3)

**Version control** records every change to your files so you can see history, undo mistakes, and work
in parallel with others.

| Type | How it works | Example |
|---|---|---|
| Local | history kept on one computer | RCS |
| Centralized | one server holds the history; you check files out | SVN, Perforce |
| **Distributed** | **every clone has the full history**; you sync with remotes | **Git**, Mercurial |

**Git vs GitHub:** Git is the tool on your computer. GitHub/GitLab/Bitbucket host remote repositories
and add pull requests, issues and CI.

### The three states (and three places)
```text
 working directory  ──git add──▶  staging area (index)  ──git commit──▶  repository (.git)
   (modified)                        (staged)                              (committed)
                                                            ──git push──▶  remote (GitHub)
```
- **Modified:** you changed the file but haven't staged it.
- **Staged:** marked to go into the next commit (`git add`).
- **Committed:** safely stored in your local history.

### First-time setup
```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
git config --global init.defaultBranch main
```

### Starting
```bash
git init                     # turn the current folder into a repository
git clone <url>              # copy an existing repository (with full history)
```

## The daily workflow (GitHub flow: what most teams use)

`main` is always working and deployable. Every change happens on a short-lived branch and comes back
through a **pull request (PR)**.

```bash
git switch main
git pull                                   # 1. start from the latest main
git switch -c feature/login-rate-limit     # 2. new branch for one task
# ...edit code, run tests...
git status                                 # 3. what changed?
git diff                                   #    see the exact lines
git add src/auth.py tests/test_auth.py     # 4. stage what belongs in this commit
git commit -m "feat(auth): limit login attempts to 5 per minute"
git push -u origin feature/login-rate-limit   # 5. publish the branch
# 6. open a pull request on GitHub, ask for review, fix comments, merge
git switch main && git pull                # 7. update, delete the old branch
git branch -d feature/login-rate-limit
```

**Other strategies you may meet:** *Git Flow* (long-lived `develop` + `release/*` branches; older or
release-heavy teams) and *trunk-based development* (tiny branches merged to `main` daily, with feature flags).

## Branch names and commit messages

Branches: `feature/<short-description>`, `fix/<bug>`, `docs/...`, `chore/...`, often with a ticket number:
`fix/JIRA-142-null-email`.

Commit messages: many teams use **Conventional Commits**:
```text
feat: add pagination to GET /books
fix(api): return 404 instead of 500 for unknown book id
docs: explain how to run the tests
refactor: move price calculation into CartService
test: cover expired tokens
chore: update dependencies
```
- Short summary line (≤ 72 chars), imperative mood ("add", not "added").
- One logical change per commit. "Fix typo + new feature + reformat everything" is three commits.
- Commit often locally; push at least daily so your work is backed up.

## Pull requests and code review

A good PR:
- is **small** (under ~400 changed lines is reviewable; 2,000 lines will be skimmed),
- has a description: **what** changed, **why**, **how to test**, screenshots for UI,
- passes tests/CI before you ask for review,
- links the ticket/issue.

When reviewing (DevNet "code review"): check correctness, readability, tests, security (input validation,
secrets), and naming. Comment on the code, not the person; ask questions ("What happens if `items` is empty?").

## Merge conflicts, step by step

A conflict happens when two branches changed the same lines.
```bash
git switch feature/my-work
git pull origin main         # or: git merge main
# CONFLICT (content): Merge conflict in src/app.js
```
```text
<<<<<<< HEAD
const timeout = 5000;        # your version
=======
const timeout = 10000;       # the version from main
>>>>>>> main
```
1. Open each conflicted file (`git status` lists them). VS Code shows *Accept Current / Incoming / Both*.
2. Edit to the correct final code and **delete the markers**.
3. Run the tests.
4. `git add <file>` then `git commit` (or `git rebase --continue` during a rebase).
5. Unsure? `git merge --abort` puts everything back.

Avoid conflicts: pull `main` into your branch often, keep branches short-lived, don't reformat whole files in a feature PR.

## Merge vs rebase

- `git merge main`: keeps history exactly as it happened, adds a merge commit. Always safe.
- `git rebase main`: replays your commits on top of the latest main, giving a straight line of history.
- **Golden rule:** only rebase commits that **only you** have (not yet pushed, or your own branch).
  Never rebase `main` or a branch others work on; it rewrites history.
- Many teams use **Squash and merge** on GitHub: the whole PR becomes one commit on main.

## Undoing things (the most useful section)

| Situation | Command |
|---|---|
| Throw away changes in a file (not staged) | `git restore <file>` |
| Unstage a file (keep the changes) | `git restore --staged <file>` |
| Fix the last commit's message or add a forgotten file (**not pushed yet**) | `git add <file>` then `git commit --amend` |
| Undo the last commit but keep the changes (**not pushed**) | `git reset --soft HEAD~1` |
| Undo a commit that is **already pushed** | `git revert <commit>` (makes a new commit that reverses it) |
| Put work aside to switch branches | `git stash` … later `git stash pop` |
| "I lost a commit!" | `git reflog` shows everything HEAD pointed to; `git switch -c rescue <hash>` |
| Committed to `main` by mistake (not pushed) | `git branch feature/x` then `git reset --hard origin/main` (your commit is now on feature/x) |

`git reset --hard` and `git push --force` **destroy work**. Use `git push --force-with-lease` only on your own branch.

## Secrets: never commit them

- Put `.env`, keys and credentials in `.gitignore` **before** the first commit.
- Commit `.env.example` with placeholder values.
- If a secret was pushed: **rotate it immediately** (create a new key, revoke the old one). Deleting the
  file or rewriting history is not enough; bots scan GitHub within minutes.

## Releases and tags

```bash
git tag -a v1.2.0 -m "Release 1.2.0"
git push origin v1.2.0
```
**Semantic versioning** `MAJOR.MINOR.PATCH`: breaking change → major, new feature → minor, bug fix → patch.

## Contributing to someone else's project (fork workflow)
1. **Fork** on GitHub (your own copy) → `git clone` your fork.
2. `git remote add upstream <original-url>` to get future updates: `git pull upstream main`.
3. Branch, commit, push to your fork, open a PR to the original repository.

## Command cheat sheet

```bash
git status                     git log --oneline --graph --all
git diff / git diff --staged   git show <commit>
git branch -a                  git switch <branch> / git switch -c <new>
git remote -v                  git fetch (download without merging) / git pull (fetch + merge)
git blame <file>               # who changed each line, and in which commit
```

## Practice routine (20 minutes)

1. Create a folder, `git init`, add a README, commit.
2. Make branch `feature/a`, change line 1, commit. Switch to `main`, change line 1 differently, commit.
3. `git merge feature/a` → resolve the conflict by hand → commit.
4. Make a bad commit, then undo it with `git revert`. Make another, undo it with `git reset --soft HEAD~1`.
5. Push to a new GitHub repository and open a PR from a branch, even if you merge it yourself.
