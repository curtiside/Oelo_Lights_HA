# Developer Guide

Development and testing tools for Oelo Lights Home Assistant integration.

## Quick Start

```bash
make setup && make start
```

See `Makefile` for commands.

## Testing

All test files in `test/` directory. See inline documentation:

```bash
head -100 test/test_integration.py
head -100 test/test_workflow.py
head -100 test/test_user_workflow.py
head -100 test/test_helpers.py
```

### Test Structure

1. **test_integration.py** - Fast unit tests (no UI, no container)
   - Controller connectivity, imports, config flow validation, pattern utils, services, storage

2. **test_workflow.py** - Pattern logic unit tests (no UI, no container)
   - Pattern capture/rename/apply logic validation

3. **test_user_workflow.py** - Complete end-to-end test (container + UI)
   - Container management, onboarding, HACS installation, integration installation, device configuration, pattern workflow

### Running Tests

**Run all tests:**
```bash
make test-all
# OR
python3 test/run_all_tests.py
```

**Run end-to-end test (complete user workflow):**
```bash
python3 test/test_user_workflow.py --clean-config
```

**Run individual tests:**
```bash
python3 test/test_integration.py
python3 test/test_workflow.py
python3 test/test_user_workflow.py [--clean-config] [--keep-container] [--skip-patterns]
```

## Development Environment

### Updating Integration Code

After code changes:
1. HACS: Redownload integration (HACS → Integrations → oelo_lights_ha → Redownload)
2. Restart HA or Reload integration (Settings → Devices & Services → oelo_lights_ha → Reload)

### Docker Setup

Uses Docker Compose for local HA testing. See `docker-compose.yml`.

### Makefile Commands

- `make setup` - Copy integration and test files to `config/`
- `make start` - Start HA container
- `make stop` - Stop container
- `make logs` - View HA logs
- `make clean` - Remove container and `config/` directory
- `make test` - Quick test (setup, start, check logs)

## Code Documentation

All documentation is inline. See module docstrings:

```bash
head -200 custom_components/oelo_lights/__init__.py
head -200 custom_components/oelo_lights/config_flow.py
head -200 custom_components/oelo_lights/services.py
```

## Project Structure

- `custom_components/oelo_lights/` - Integration code
- `test/` - Test files
- `config/` - Docker test environment (gitignored)
- `Makefile` - Development commands
- `docker-compose.yml` - Local HA testing setup
