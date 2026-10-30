PYTHON ?= python
.PHONY: verify smoke run all export figures inputs integrity
verify smoke run all export figures inputs integrity:
	$(PYTHON) reproduce.py $@
