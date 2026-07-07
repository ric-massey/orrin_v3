# Contributing

Orrin is a single-developer experimental research project, but issues, experiments, forks, and pull requests are welcome.

## Development Setup

```bash
git clone https://github.com/ric-massey/orrin_v3.git
cd orrin_v3

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Node.js + npm are only needed if you are developing or building the frontend from source.

## Running Tests

```bash
pytest
pytest tests/brain
```

Keep the test suite green before opening a pull request.

## Conventions

- Resolve runtime state paths through the existing path helpers instead of hand-built paths.
- Keep the system symbolic-first. LLMs should remain explicit, gated tools.
- Treat claims about cognition carefully. Prefer operational evidence over anthropomorphic language.
- Do not commit secrets. Keep API keys in `.env` or a local secret store (see [SECURITY.md](SECURITY.md)).
