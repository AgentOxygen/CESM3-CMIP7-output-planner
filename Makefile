.PHONY: test build dev shell import-cmip7 stamp

DC = docker compose run --rm dev

# Run the test suite.
test:
	$(DC) pytest -q

# Regenerate docs/data.json from data/cmip7_request.yaml. Commit the result.
build:
	$(DC) python build.py

# Record the current git commit in docs/version.json (shown on the page, written into the namelists).
# Runs on the host, not in Docker: the container has no git. It names the commit you are building on,
# so the committed file points at its parent; run it before committing.
stamp:
	python3 tools/stamp_version.py

# Serve the site at http://localhost:8000, rebuilding docs/data.json whenever
# data/*.yaml changes. The page reloads itself when either changes.
dev:
	docker compose run --rm --service-ports dev python tools/dev.py

shell:
	$(DC) bash

# Regenerate data/cmip7_request.yaml from the (local-only, not committed)
# CMIP7 request CSVs in reference/. No-ops if you don't have them --
# see tools/import_cmip7.py.
import-cmip7:
	$(DC) python tools/import_cmip7.py
