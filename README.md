# Secret Santa

A command-line tool that runs a Secret Santa lottery for families.
Each participant is randomly assigned one person to buy a gift for, with the constraint that **partners are never paired together**.

---

## Features

- **Constraint-based draw** — exclude specific people from being assigned to each other (ideal for couples or siblings who already exchange gifts separately)
- **Optional email delivery** — sends personalised notifications to every participant via Gmail SMTP
- **File output** — writes a per-person `.txt` result file to an `out/` folder so you can hand-deliver assignments without email
- **Zero dependencies** — runs on the Python standard library only
- **Deadlock-safe** — automatically detects and recovers from impossible draw states and retries

---

## Requirements

- Python **3.7** or later
- No third-party packages required

---

## Installation

### Via pip (recommended)

```bash
git clone https://github.com/your-username/secret_santa.git
cd secret_santa
pip install .
```

After installing, the `secret-santa` command is available system-wide:

```bash
secret-santa participants.json message.html
```

### Run directly without installing

```bash
python secret_santa.py participants.json message.html
```

---

## Setup

### 1. Participants JSON file

Create a JSON file listing every participant. Each entry must include:

| Field         | Type            | Description                                         |
|---------------|-----------------|-----------------------------------------------------|
| `name`        | string          | Display name used in filenames and email            |
| `email`       | string          | Email address for notifications                     |
| `not_allowed` | array of strings | Names this person must **not** be assigned to gift |

Partners should list each other in `not_allowed` so they are never paired:

```json
[
  {"name": "Alice",   "not_allowed": ["Bob"],     "email": "alice@example.com"},
  {"name": "Bob",     "not_allowed": ["Alice"],   "email": "bob@example.com"},
  {"name": "Charlie", "not_allowed": ["Diana"],   "email": "charlie@example.com"},
  {"name": "Diana",   "not_allowed": ["Charlie"], "email": "diana@example.com"},
  {"name": "Eve",     "not_allowed": [],          "email": "eve@example.com"},
  {"name": "Frank",   "not_allowed": [],          "email": "frank@example.com"}
]
```

A ready-to-use example is available at [`examples/family.json`](examples/family.json).

### 2. Message template

Write a `.txt` or `.html` file that will be sent (or saved to disk) as the notification for each participant. Use these placeholders:

| Placeholder | Replaced with        |
|-------------|----------------------|
| `^`         | The **giver's** name |
| `*`         | The **receiver's** name |

**Plain-text example:**

```
Dear ^,

The Secret Santa draw has been made — the secret is yours to keep!
This year you will be buying a gift for: *

Happy shopping and Merry Christmas!
```

Ready-to-use templates are available in the [`examples/`](examples/) folder:

- [`examples/message.txt`](examples/message.txt) — plain text
- [`examples/message.html`](examples/message.html) — styled HTML email

### 3. Gmail credentials (required only for `-e`)

If you want to send emails, set two environment variables **before** running the tool:

```bash
export SANTA_EMAIL_ADDRESS="your.address@gmail.com"
export SANTA_EMAIL_PASSWORD="your-app-password"
```

> **Important:** Use a [Gmail App Password](https://support.google.com/accounts/answer/185833), not your regular account password.
> An App Password is a 16-character code you generate in your Google Account security settings. This is required because Google does not allow direct login via SMTP with a normal password.

---

## Usage

```
secret-santa <list> <message> [-e] [-v]
```

| Argument / Flag | Description                                                  |
|-----------------|--------------------------------------------------------------|
| `list`          | Path to the participants JSON file                           |
| `message`       | Path to the TXT or HTML message template                     |
| `-e` / `--email`| Send email notifications to all participants after the draw  |
| `-v`            | Verbose output (INFO level)                                  |
| `-vv`           | Debug output (DEBUG level, very detailed)                    |

### Examples

**Run the draw and write result files to `out/`:**

```bash
secret-santa examples/family.json examples/message.txt
```

**Run the draw and email all participants:**

```bash
export SANTA_EMAIL_ADDRESS="santa@gmail.com"
export SANTA_EMAIL_PASSWORD="abcd efgh ijkl mnop"

secret-santa examples/family.json examples/message.html -e
```

**Inspect what is happening with verbose logging:**

```bash
secret-santa examples/family.json examples/message.txt -vv
```

---

## Output

After running, an `out/` directory is created containing one `.txt` file per participant:

```
out/
├── Alice.txt
├── Bob.txt
├── Charlie.txt
├── Diana.txt
├── Eve.txt
└── Frank.txt
```

Each file contains the participant's name, their assigned receiver, and their email address — useful for hand-delivering results without sending emails.

---

## How the algorithm works

The draw uses a **randomised constraint-satisfaction** approach:

1. All participants are placed in a pool of available receivers.
2. For each giver (in order), a random candidate is drawn from the pool.
3. The candidate is validated: they must not be the giver themselves, and must not appear in the giver's `not_allowed` list.
4. If valid, the candidate is removed from the pool and assigned to the giver.
5. If too many consecutive invalid draws occur for a single giver (**deadlock**), the entire draw is discarded, all assignments are reset, and the process starts again from step 1.
6. The loop continues until every participant has a valid assignment.

This guarantees a fully random result that respects all constraints without systematic bias.

---

## Logging

A `secret_santa.log` file is written to the working directory on every run. It captures all DEBUG and INFO messages regardless of the `-v` flag, making it useful for auditing draws or diagnosing unexpected results.

---

## Contributing

Bug reports and pull requests are welcome. Please open an issue on GitHub.

---

## License

GNU General Public License v3 — see [LICENSE](LICENSE) for details.
