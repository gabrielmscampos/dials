import json
import os.path

from .env import etl_config_fpath


# If etl config file path is specific but dot no exists, stop the program
if os.path.exists(etl_config_fpath) is False:
    raise Exception("etl config file not found in specified path.")

# Read configuration from object
with open(etl_config_fpath) as f:
    config_contents = json.load(f)

# Expose objects
common_chunk_size = config_contents["common_chunk_size"]
common_indexer_queue = config_contents["common_indexer_queue"]
dev_env_label = config_contents["dev_env_label"]
downloader_bulk_suffix = config_contents["downloader_bulk_suffix"]
downloader_priority_suffix = config_contents["downloader_priority_suffix"]
era_cmp_pattern = config_contents["era_cmp_pattern"]
priority_era = config_contents["priority_era"]
th1_types = config_contents["th1_types"]
th2_types = config_contents["th2_types"]
th2_chunk_size = config_contents["th2_chunk_size"]
workspaces = config_contents["workspaces"]

# List all primary datasets and generate queue names
primary_datasets = [elem for ws in workspaces for elem in ws["primary_datasets"]]
primary_datasets = sorted(set(primary_datasets))
pds_queues = {
    primary_dataset: {
        "bulk_queue": f"{primary_dataset}{downloader_bulk_suffix}",
        "priority_queue": f"{primary_dataset}{downloader_priority_suffix}",
    }
    for primary_dataset in primary_datasets
}

# We can delete config_contents from memory
del config_contents
