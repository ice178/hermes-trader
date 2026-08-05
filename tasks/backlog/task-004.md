# Task: Deploy production bot from GitHub Actions

## Status

Backlog

Owner: Tomasso / Codex

Updated: 2026-08-03

## Context

The Telegram bot is deployed on an Ubuntu server under `systemd`. Application
code lives at `/opt/hermes-trading/app`, runtime configuration lives outside Git
at `/etc/hermes-trading/hermes-signals-bot.env`, and the timer starts
`hermes-signals-bot.service` on the Madrid schedule.

Releases currently require several manual SSH commands: stop the timer, pull
Git, install the package, copy systemd units, reload systemd, run a check, and
start the timer again. This is workable for recovery but inconvenient and easy
to execute incompletely.

GitHub supports manually triggered Actions workflows through
`workflow_dispatch`. This can provide a visible **Run workflow** button without
deploying every push automatically.

References:

- [Manually running a workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [GitHub Actions deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
- [Using secrets in GitHub Actions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions)

## Problem

Production releases are too manual. A missed command can leave old code, stale
systemd units, or a stopped timer on the server. Connecting GitHub Actions
directly as `root`, disabling SSH host verification, or copying Telegram secrets
into GitHub would make deployment easier at the cost of unnecessary security
risk.

## Goal

Provide one intentional production release action:

1. Push or merge a tested change into `main`.
2. Open GitHub → Actions → **Deploy Hermes Bot**.
3. Click **Run workflow** for `main`.
4. GitHub runs the test suite.
5. If tests pass, GitHub connects to the Ubuntu server over verified SSH.
6. The server deploys the exact selected commit, refreshes dependencies and
   systemd units, and restores the timer.
7. The Actions run reports the deployed commit, service result, next timer run,
   and any failure.

The first version should remain manually triggered. Automatic deployment on
every push can be considered later after the manual workflow is proven stable.

## Non-goals

- Moving Telegram credentials or bot configuration from the server to GitHub.
- Deploying on every push to `main`.
- Introducing Docker, Kubernetes, Ansible, Terraform, or a third-party CI/CD
  service.
- Adding a self-hosted GitHub Actions runner.
- Changing signal detection or trading behavior.
- Creating staging infrastructure.
- Allowing arbitrary branches or pull-request code to access production SSH
  secrets.

## Desired operator workflow

### Normal release

1. Confirm the intended changes are committed and pushed to `main`.
2. Open the repository on GitHub.
3. Open **Actions** and select **Deploy Hermes Bot**.
4. Click **Run workflow** and select `main`.
5. Confirm the optional input `run_live_scan` is disabled unless a real
   Telegram-producing scan is intentionally required.
6. Start the workflow.
7. Wait for the `test` job and then the `deploy` job.
8. Check the workflow summary for:
   - deployed commit SHA;
   - successful dependency installation;
   - successful systemd unit validation;
   - active timer;
   - next scheduled run.

### What must happen automatically

- Only one production deployment may run at a time.
- Tests must finish successfully before SSH credentials become useful to the
  deployment job.
- The deployment must use the exact workflow commit SHA, not an unspecified
  latest checkout.
- SSH must validate the server host key.
- The timer must be stopped while files and units are being updated.
- `/etc/hermes-trading/hermes-signals-bot.env` must never be replaced.
- A normal deployment must not run a live market scan by default, because a
  release around a candle close could duplicate a real Telegram notification.
- The timer must be enabled and its next run printed after success.
- A failed deployment must produce an obvious red Actions result and follow the
  agreed recovery behavior rather than silently continuing.

## Proposed architecture

```text
Developer
   │ push/merge main
   ▼
GitHub repository
   │ Actions → Run workflow
   ▼
GitHub-hosted runner
   ├── checkout exact commit
   ├── install project + pytest
   ├── run python3 -m pytest
   └── SSH with dedicated deployment key
           │
           ▼
Ubuntu: hermes-deploy user
   └── sudo one root-owned deployment command
           │
           ▼
/usr/local/sbin/deploy-hermes-trading
   ├── validate requested commit
   ├── update /opt/hermes-trading/app as hermes
   ├── install package into existing .venv
   ├── install and validate systemd units
   ├── reload systemd
   └── enable/start timer and print status
```

Use separate identities for separate purposes:

- `hermes` remains the non-login runtime owner used by the systemd service and
  by Git when updating `/opt/hermes-trading/app`;
- `hermes-deploy` is an SSH login used only by GitHub Actions;
- GitHub Actions receives permission to invoke one root-owned deployment
  command through `sudo`; it does not receive an unrestricted root shell;
- the server's existing read-only GitHub deploy key remains responsible for
  fetching the private repository;
- Telegram credentials remain only in
  `/etc/hermes-trading/hermes-signals-bot.env`.

## Planned repository files

```text
.github/workflows/deploy-production.yml
docs/github-actions-deployment.md
```

If a versioned example of the server-side deployment command is added, place it
under `deploy/` for review, but do not let the workflow install and immediately
execute an arbitrary root script from the commit being deployed. The executable
copy in `/usr/local/sbin` must be installed manually by an administrator and
owned by `root:root`.

Update `docs/server-deployment.md` so that:

- GitHub Actions becomes the normal release path;
- manual SSH deployment remains the recovery path;
- the two procedures do not contradict each other.

## One-time setup

The exact commands must be reviewed against the real server before execution.
Placeholders such as `<server-host>` must not be copied literally.

### 1. Create a dedicated inbound deployment key

Generate the key on a trusted local machine. Do not reuse a personal key or the
server's outbound GitHub deploy key.

```bash
ssh-keygen -t ed25519 \
  -C "github-actions-hermes-production" \
  -f ~/.ssh/hermes-github-actions
```

This creates:

- `~/.ssh/hermes-github-actions` — private key, later stored as a GitHub secret;
- `~/.ssh/hermes-github-actions.pub` — public key, installed on the server.

Never commit either file. Delete the local private-key copy after GitHub Secrets
and recovery storage have been verified.

### 2. Create a dedicated server login

On Ubuntu, create a normal login account without giving it ownership of the bot
or membership in broad administrative groups:

```bash
sudo adduser --disabled-password --gecos "" hermes-deploy
sudo install -d -o hermes-deploy -g hermes-deploy -m 0700 \
  /home/hermes-deploy/.ssh
sudoedit /home/hermes-deploy/.ssh/authorized_keys
sudo chown hermes-deploy:hermes-deploy \
  /home/hermes-deploy/.ssh/authorized_keys
sudo chmod 0600 /home/hermes-deploy/.ssh/authorized_keys
```

Paste only the public key. Prefix it with SSH restrictions where supported:

```text
restrict ssh-ed25519 <public-key-data> github-actions-hermes-production
```

Do not enable SSH login for the runtime `hermes` service account merely to make
Actions work.

### 3. Install a root-owned deployment command

Create `/usr/local/sbin/deploy-hermes-trading` through `sudoedit`. Its eventual
implementation must:

1. enable strict shell behavior;
2. accept exactly one 40-character hexadecimal commit SHA, plus an optional
   explicit smoke-scan flag;
3. reject extra or malformed arguments;
4. confirm `/opt/hermes-trading/app` is the expected Git worktree;
5. fetch `origin/main` as `hermes`;
6. confirm the requested commit exists and is reachable from `origin/main`;
7. record the currently deployed commit for diagnostics and recovery;
8. stop `hermes-signals-bot.timer` only after validation succeeds;
9. check out the exact commit as `hermes`;
10. install the package into `/opt/hermes-trading/app/.venv`;
11. install both repository systemd units into `/etc/systemd/system`;
12. run `systemctl daemon-reload`;
13. run `systemd-analyze verify` for the service and timer;
14. optionally start the oneshot service only when `run_live_scan` was
    explicitly requested;
15. enable and start the timer;
16. print the deployed SHA, service result, timer state, and next scheduled run.

Set restrictive ownership and permissions:

```bash
sudo chown root:root /usr/local/sbin/deploy-hermes-trading
sudo chmod 0755 /usr/local/sbin/deploy-hermes-trading
```

The deployment command must use absolute paths and must not evaluate arbitrary
shell text supplied by the workflow.

### 4. Restrict sudo

Create `/etc/sudoers.d/hermes-deploy` with `visudo`:

```bash
sudo visudo -f /etc/sudoers.d/hermes-deploy
```

The rule should allow `hermes-deploy` to run only the reviewed deployment
command without a password. If argument wildcards are required, the deployment
command itself must strictly validate the SHA and optional flag.

Conceptual rule to review during implementation:

```text
hermes-deploy ALL=(root) NOPASSWD: /usr/local/sbin/deploy-hermes-trading *
```

Validate it before ending the root session:

```bash
sudo visudo -cf /etc/sudoers.d/hermes-deploy
sudo -l -U hermes-deploy
```

Confirm that the account cannot run unrelated commands with `sudo`.

### 5. Record and verify the SSH host key

Do not use `StrictHostKeyChecking=no`. Obtain the server's Ed25519 host public
key through an already trusted channel and compare its fingerprint with:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Create a `known_hosts` line for the exact public host name or IP and SSH port.
Store that complete line in GitHub rather than calling `ssh-keyscan` blindly on
every deployment.

### 6. Configure GitHub Secrets

In GitHub open repository **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `PRODUCTION_SSH_HOST` | Public DNS name or IP of the Ubuntu server |
| `PRODUCTION_SSH_PORT` | SSH port, normally `22` |
| `PRODUCTION_SSH_USER` | `hermes-deploy` |
| `PRODUCTION_SSH_PRIVATE_KEY` | Full private deployment key including header and footer |
| `PRODUCTION_SSH_KNOWN_HOSTS` | Verified `known_hosts` line for the server |

Do not add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, or the production env file
to GitHub. They already live in the correct place on the server.

Repository-level Actions secrets are the baseline because availability of
environment secrets and approval rules depends on repository visibility and the
GitHub plan. If the repository supports a protected `production` Environment,
prefer it and restrict deployments to `main`; the workflow design must still
work with repository secrets if those plan features are unavailable.

### 7. Test SSH before enabling the workflow

From a trusted local machine, test the new private key against the new account
and confirm it has only the intended sudo capability. Do not test by pasting the
private key into a shell command or chat.

## Intended GitHub Actions workflow

The implementation should follow this shape; exact action versions must be
reviewed when task implementation starts.

```yaml
name: Deploy Hermes Bot

on:
  workflow_dispatch:
    inputs:
      run_live_scan:
        description: Run one real signal scan after deployment
        required: true
        default: false
        type: boolean

permissions:
  contents: read

concurrency:
  group: hermes-production
  cancel-in-progress: false

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<reviewed-version>
      - uses: actions/setup-python@<reviewed-version>
        with:
          python-version: "3.12"
          cache: pip
      - run: python -m pip install --upgrade pip
      - run: python -m pip install --editable . pytest
      - run: python -m pytest

  deploy:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    # Add `environment: production` when supported and configured.
    steps:
      - name: Configure SSH
        # Write the private key and verified known_hosts data with mode 0600.
        # Pass secrets through step environment variables; never print them.

      - name: Deploy exact commit
        # Connect using PRODUCTION_SSH_HOST/PORT/USER.
        # Run only:
        # sudo /usr/local/sbin/deploy-hermes-trading <github.sha> [smoke flag]

      - name: Write deployment summary
        # Append the SHA and server-reported status to $GITHUB_STEP_SUMMARY.
```

Implementation rules for the workflow:

- Pin first-party actions to reviewed major versions or immutable commit SHAs.
- Do not introduce a third-party SSH action when the runner's standard `ssh`
  client is sufficient.
- Use `github.sha` and quote it as data.
- Pass secrets through environment variables and disable command tracing.
- Create `~/.ssh` with mode `0700`, private key with `0600`, and `known_hosts`
  with `0600`.
- Use `BatchMode=yes` so a deployment cannot hang waiting for input.
- Set a connection timeout.
- Restrict deployment to `main` even though the button offers branch selection.
- Keep `cancel-in-progress: false` so one release cannot interrupt another.
- Use the minimum `GITHUB_TOKEN` permission: `contents: read`.
- Do not run workflows containing production secrets for pull requests or forks.

## Failure and rollback considerations

Before implementation, choose and document one deterministic failure policy.
Recommended policy:

1. Validate and fetch before stopping the timer.
2. Record the previous commit SHA.
3. If failure occurs before the checkout changes, leave the old timer running.
4. If failure occurs after code or units change, attempt one rollback to the
   previous SHA, reinstall its package and units, and restart its timer.
5. If rollback also fails, leave the timer stopped, return a failing Actions
   result, and print exact manual recovery commands. Do not repeatedly run a
   partially deployed bot.

The deployment command should prevent concurrent runs locally as a second layer
of protection, for example with `flock`, because GitHub concurrency does not
protect against a simultaneous manual SSH deployment.

Rollback must be possible without rewriting Git history. Preferred UX after the
first implementation:

- workflow output records previous and deployed SHAs;
- a documented manual recovery command can deploy a previously known-good
  commit reachable from `main`;
- adding a separate **Rollback Hermes Bot** workflow is deferred until normal
  releases have been exercised successfully.

## Open questions

- [ ] Confirm the server's public SSH host and port without storing them in this task file.
- [ ] Confirm whether the GitHub repository is private and which Environment features the current plan supports.
- [ ] Decide whether the first implementation includes automatic rollback or initially fails safe with the timer stopped.
- [ ] Confirm that deployment is restricted to `main` only.
- [ ] Confirm that `run_live_scan` defaults to `false` to avoid duplicate notifications.
- [ ] Decide whether the server SSH key should be rotated immediately after the first successful Actions deployment test.

## Acceptance criteria

- [ ] `.github/workflows/deploy-production.yml` provides a manual **Run workflow** action.
- [ ] The workflow can deploy only a commit from `main`.
- [ ] The full Python test suite must pass before deployment starts.
- [ ] Concurrent production deployments are prevented.
- [ ] GitHub connects as a dedicated non-root deployment user.
- [ ] SSH host verification uses a pinned, previously verified host key.
- [ ] GitHub stores only deployment connection secrets, not Telegram credentials.
- [ ] The deployment user has no unrestricted `sudo` access.
- [ ] The server validates the commit SHA and deploys that exact commit.
- [ ] Production environment configuration is preserved outside the checkout.
- [ ] Both systemd units are updated and validated during deployment.
- [ ] A regular deployment does not perform a live Telegram-producing scan.
- [ ] Successful output includes the deployed SHA, active timer, and next run.
- [ ] Failure behavior and manual recovery are documented and tested safely.
- [ ] `docs/github-actions-deployment.md` covers one-time setup, normal release,
  troubleshooting, key rotation, and rollback.
- [ ] `docs/server-deployment.md` identifies Actions as the normal release path
  and manual SSH as recovery.
- [ ] No secrets or private key material are committed or printed in logs.

## Implementation plan

1. Reconfirm server paths, service names, SSH port, repository visibility, and
   preferred rollback policy.
2. Design and review the root-owned deployment command, including strict input
   validation, exact-SHA deployment, locking, failure stages, and output.
3. Add the reviewed server command example under `deploy/` if useful.
4. Write `docs/github-actions-deployment.md` with the one-time commands above.
5. Perform the server setup manually: account, authorized key, root-owned
   command, sudoers rule, and verified host key.
6. Add GitHub Secrets through the GitHub UI; never paste their values into task
   files, commits, terminal history, or chat.
7. Add `.github/workflows/deploy-production.yml` using only first-party actions
   and the standard SSH client.
8. Add lightweight repository tests that assert the workflow remains manual,
   main-only, minimally permissioned, and references the expected deploy command.
9. Push the workflow to `main`; the button only appears for a
   `workflow_dispatch` workflow present on the default branch.
10. Run the first deployment with `run_live_scan=false` while keeping a separate
    trusted SSH session open for recovery.
11. Verify the deployed SHA, installed units, timer status, next Madrid run, and
    journald after the next scheduled scan.
12. Rotate the Actions deployment key if it was exposed during setup, update the
    operational docs, and move the task to Review.

## Test plan

### Repository checks

- Run `python3 -m pytest` before adding server access.
- Review the workflow trigger, permissions, branch guard, concurrency group,
  secret references, and SSH options.
- Confirm `.env`, private keys, and generated SSH files are ignored and absent
  from `git diff --cached`.
- Validate YAML through GitHub after the initial push; do not add a new project
  dependency solely for YAML parsing.

### Server setup checks

- `sshd` accepts the new key for `hermes-deploy` and rejects password login.
- `sudo -l -U hermes-deploy` lists only the deployment command.
- `visudo -cf /etc/sudoers.d/hermes-deploy` succeeds.
- The deployment command rejects missing, malformed, extra, and non-main SHAs.
- The deployment command cannot overwrite
  `/etc/hermes-trading/hermes-signals-bot.env`.
- `systemd-analyze verify` succeeds for both installed units.

### First release check

- Trigger from `main` with `run_live_scan=false`.
- Confirm tests complete before the deploy job.
- Confirm no unexpected Telegram message is sent by the deployment itself.
- Compare the Actions SHA with:

  ```bash
  sudo -u hermes git -C /opt/hermes-trading/app rev-parse HEAD
  ```

- Confirm:

  ```bash
  systemctl is-enabled hermes-signals-bot.timer
  systemctl is-active hermes-signals-bot.timer
  systemctl list-timers hermes-signals-bot.timer
  sudo journalctl -u hermes-signals-bot.service -n 100 --no-pager
  ```

- Exercise one controlled failure before considering the workflow stable, such
  as requesting a rejected SHA, and verify the timer/failure policy behaves as
  documented.

## Agent instructions

Read this task and `docs/server-deployment.md` before implementation. Reinspect
the current repository and do not assume server commands in this draft exactly
match external state. Never request or print private key contents, Telegram
credentials, the production env file, or secret values. Do not weaken SSH host
verification. Do not grant unrestricted root SSH or unrestricted passwordless
sudo. Do not enable push-triggered production deployment without explicit user
approval.

Repository changes alone cannot finish this task: the user must perform or
explicitly authorize the GitHub UI and Ubuntu server configuration. Keep the
task Active until the button has completed a real deployment and the installed
timer has been verified.

## Review notes

Pending implementation.

## Handoff

Task specification created. Next step is to review the open questions with
Tomasso, then implement the server-side restricted command and GitHub workflow
in small, separately reviewable steps.
