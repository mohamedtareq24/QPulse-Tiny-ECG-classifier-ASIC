CONFIG_DIR := config_stages
MANIFEST := all.json
CONFIG := config.json
MERGER := merge_configs.py

CONFIG_INPUTS := \
	$(CONFIG_DIR)/all.json \
	$(CONFIG_DIR)/1_syn.json \
	$(CONFIG_DIR)/2_floorplan.json \
	$(CONFIG_DIR)/3_powerplan.json \
	$(CONFIG_DIR)/4_placement.json \
	$(CONFIG_DIR)/5_cts.json \
	$(CONFIG_DIR)/6_routing.json \
	$(CONFIG_DIR)/7_signoff.json \
	$(CONFIG_DIR)/eco.json

.PHONY: all config force-config clean-config lock-config unlock-config status

all: config

config: $(CONFIG)

$(CONFIG): $(MERGER) $(CONFIG_INPUTS)
	@chmod u+w "$@" 2>/dev/null || true
	python3 ./$(MERGER) --manifest $(MANIFEST) --output "$@"
	chmod a-w "$@"
	@echo "Updated and locked $(CONFIG)"

force-config:
	@$(MAKE) --no-print-directory clean-config
	@$(MAKE) --no-print-directory config

clean-config:
	@chmod u+w "$(CONFIG)" 2>/dev/null || true
	rm -f "$(CONFIG)"

lock-config:
	chmod a-w "$(CONFIG)"

unlock-config:
	chmod u+w "$(CONFIG)"

status:
	ls -l "$(CONFIG)"
