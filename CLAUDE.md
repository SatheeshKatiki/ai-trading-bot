# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands
- **Build**: `npm run build` (or `python setup.py build` if applicable)
- **Lint**: `eslint --ext .js,.ts **/*.js ` (adjust based on file extensions)
- **Test**: `npm test` (or `pytest` for Python-based projects)
- **Run single test**: `npm run test:unit` (or `pytest test_module.py`)

## High-Level Code Architecture
The repository is structured with clear separation between:

1. **Frontend**: Contains React components (src/client), Redux store logic, and API interfaces
2. **Backend**: Node.js services (src/server) handling business logic and database interactions
3. **Shared**: Common types, utilities, and configuration (src/shared)

Key components:
- Core API: `src/server/api/routes.ts` defines all RESTful endpoints
- Data layer: SQLite database migrations in `src/database/migrations`
- Auth system: JWT-based authentication in `src/server/auth`

## Rules and Guidelines
- **Cursor Rules**: Defined in `.cursor/rules/` (e.g., style conventions, test requirements)
- **Copilot Instructions**: Found in `.github/copilot-instructions.md` (e.g., documentation standards)
- **README.md**: [Important sections][readme-link] summarize deployment, API usage, and contribution guidelines

### References
[readme-link]: /README.md