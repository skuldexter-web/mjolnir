# ⚡ MJOLNIR

**A local, Ollama-only terminal AI agent for Debian-based Linux.**

> *"WHAT SHOULD BE, OR SHOULD NOT."*

Built by **SⱩUⱠÐ** — [github.com/skuldexter-web](https://github.com/skuldexter-web) · [@s.k.7.l.d](https://www.instagram.com/s.k.7.l.d/)

---

## What is Mjolnir?

Mjolnir is a lightweight, fully local terminal agent. No cloud APIs, no
API keys, no telemetry — every inference call goes to a local [Ollama](https://ollama.com)
instance. It's built to run comfortably on modest hardware by capping
models at 3–14B parameters from the Qwen or Gemma families.

It gives you a structured, transparent agent loop right in your terminal:

```
[THINKING]        Reasoning about your request...
[EXECUTING TOOL]  run_command({'command': 'uname -a'})
[TERMINAL OUTPUT] Linux kali 6.x ...
[RESPONSE]        Here's what I found...
```

## Features

- **Ollama-exclusive inference** — no OpenAI/Anthropic/Groq bindings anywhere in the codebase.
- **Model allowlist** — only Qwen or Gemma family models, capped at 14B parameters, enforced in config validation.
- **Safe(r) shell tool** — destructive command patterns are denylisted outright; other risky commands require interactive confirmation.
- **File system tool** — read/write/list with a confirmation gate for writes outside `$HOME`.
- **YAML config** at `~/.config/mjolnir/config.yaml`, created with sane defaults on first run.
- **Multi-stream logging** (`session`, `tool`, `error`) with rotation, under `~/.config/mjolnir/logs/`.
- **Anonymous mode** — optionally route Ollama traffic through a local Tor SOCKS proxy (`/anon on`).
- **Global `mjolnir` command** installed to `~/.local/bin` (and symlinked to `/usr/local/bin` where possible).

## Install

```bash
git clone https://github.com/skuldexter-web/mjolnir.git
cd mjolnir
bash install.sh
```

The installer will:

1. `apt-get update` and install `python3`, `python3-pip`, `python3-venv`, `git`, `curl`.
2. Install Ollama if it isn't already present, and start the service.
3. Pull the default model (`qwen2.5:3b`).
4. Create an isolated virtualenv and install Python dependencies.
5. Install the global `mjolnir` command.

## Usage

```bash
mjolnir                          # interactive session
mjolnir -i "check disk usage"    # single non-interactive instruction
mjolnir --model qwen2.5:7b       # override model for this session
mjolnir --anon                   # route this session's Ollama traffic via Tor
```

In-session commands:

```
/help              Show available commands
/model <name>      Switch model (Qwen/Gemma, <=14B only)
/anon on|off        Toggle anonymous (Tor) mode
/clear             Clear conversation history
exit / quit         Quit
```

## Project layout

```text
mjolnir/
├── README.md
├── install.sh
├── requirements.txt
└── mjolnir/
    ├── main.py                  # CLI entrypoint
    ├── config/settings.py       # YAML config + model allowlist validation
    ├── llm/client.py            # Ollama REST client (streaming, optional Tor)
    ├── llm/templates.py         # System prompt / message building
    ├── agents/base.py           # Agent state + rolling context
    ├── agents/execution_loop.py # Think -> act -> observe -> respond loop
    ├── tools/registry.py        # Decorator-based tool registry
    ├── tools/terminal.py        # Shell execution tool (denylist + confirm)
    ├── tools/file_system.py     # Read/write/list tools
    └── interface/
        ├── banner.py            # ASCII art + gradient banner
        └── tui.py                # Rich/prompt_toolkit terminal UI
```

## Safety notes

The shell and filesystem tools are **not a sandbox**. They run with the
same privileges as whoever starts `mjolnir`. The denylist and
confirmation prompts catch obviously destructive patterns (recursive
deletes of `/`, disk-wiping `dd`, fork bombs, etc.) but are not a
security boundary against a determined or compromised model. Run
Mjolnir on systems and with permissions you're comfortable with an
autonomous local agent operating under.

## License

Apache-2.0
