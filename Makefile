# Needs make, git and Docker. On Windows, run it from Git Bash.
TOOLS_IMG := home-lab-infra-tools

.PHONY: check tools-image

## check: run every check CI runs (yamllint, shellcheck, private values) in the pinned tools image
check: tools-image
	git ls-files -z --cached --others --exclude-standard \
	  | MSYS_NO_PATHCONV=1 docker run --rm -i -e GITHUB_ACTIONS -v "$(CURDIR):/work" -w /work $(TOOLS_IMG) bash scripts/check.sh

## tools-image: build the tools image from ci/Dockerfile
tools-image:
	docker build -q -t $(TOOLS_IMG) ci
