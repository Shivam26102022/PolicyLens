# GitHub Copilot CLI Commands

These commands use the fine-grained PAT stored in the local, Git-ignored `pat.env` file. They do not use browser login or the OAuth device flow.

## 1. Go to the project

```bash
cd /home/azureuser/shivam-dev/ISO-Extraction
```

## 2. Protect the PAT file

Run this once to restrict access to your Linux user:

```bash
chmod 600 pat.env
```

Do not run `cat pat.env`, commit the file, or paste the token into a command.

## 3. Load the PAT into the current terminal

`set -a` is important because it exports the variable to the Copilot process:

```bash
set -a
source ./pat.env
set +a
```

The token must be loaded again in each new terminal.

## 4. Verify the token safely

These commands show only whether the variable is set and has the expected prefix:

```bash
if [[ -n "${COPILOT_GITHUB_TOKEN:-}" ]]; then
    echo "COPILOT_GITHUB_TOKEN is set"
else
    echo "COPILOT_GITHUB_TOKEN is not set"
fi

if [[ "${COPILOT_GITHUB_TOKEN:-}" == github_pat_* ]]; then
    echo "Token prefix is valid: github_pat_"
else
    echo "Token prefix is invalid or missing"
fi
```

## 5. Start Copilot CLI

```bash
copilot --no-auto-update --log-level none --no-remote --no-remote-export
```

Do not run `copilot login`; that starts browser or OAuth authentication.

## 6. Chec

k quota and usage

Type these commands inside the running Copilot CLI:

```text
/statusline quota ai-used
/usage
```

- `/statusline quota ai-used` shows the quota status in the bottom status bar.
- `/usage` shows current-session AI credits or premium requests and token details.
- `Session: 0 AIC used` is session usage, not the account balance.

Other useful commands:

```text
/model       # Model costs
/context     # Context-window token usage
/limits      # Current session limits
/help        # Available CLI commands
/exit        # Exit Copilot
```

Account-level plan and usage details are available at:

[https://github.com/settings/billing/plans](https://github.com/settings/billing/plans)

## 7. Run one prompt without interactive mode

```bash
copilot -p "What is 2+2?"
```

The command prints a usage summary after completion. It uses the PAT already exported in the terminal.

## 8. Limit one session's credits

The minimum session limit is 30 AI credits:

```bash
copilot --max-ai-credits 30
```

## 9. Clear the token from the current terminal

This does not delete `pat.env`; it removes the exported value from the current shell:

```bash
unset COPILOT_GITHUB_TOKEN
```

## Troubleshooting authentication

If Copilot asks you to run `/login`, the variable was probably not exported. Reload it with:

```bash
set -a
source ./pat.env
set +a
```

If authentication still fails, check these possibilities:

1. **Invalid or expired token:** create a replacement fine-grained PAT and update `pat.env`.
2. **Missing permission:** the PAT needs the GitHub fine-grained **Copilot Requests** permission.
3. **Missing license:** the GitHub account must have an active Copilot license or seat.
4. **Organization policy:** an organization administrator may block Copilot CLI or restrict Copilot usage.

Never paste the complete token into chat, shell commands, logs, or Git.
