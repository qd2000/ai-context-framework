"""Global constants shared across ACF modules."""

JSON_SCHEMA_VERSION = 1

EXIT_CHECK_FAILED = 1
EXIT_INPUT_ERROR = 2
EXIT_SAFETY_REFUSED = 3
EXIT_RUNTIME_ERROR = 70

TARGET_EXISTS_APPEND_REQUIRED = "TARGET_EXISTS_APPEND_REQUIRED"
APPEND_FORCE_CONFLICT = "APPEND_FORCE_CONFLICT"
ANCHOR_NOT_FOUND = "ANCHOR_NOT_FOUND"

LOCK_FILE_REL = ".acf.lock"

ACF_HOME_ENV = "ACF_HOME"
USAGE_LOG_CONFIG_NAME = "config.json"
USAGE_LOG_FILE_REL = "logs/usage.jsonl"
USAGE_LOCK_FILE_NAME = "usage.lock"

DEFAULT_STALE_DAYS = 14

VALID_FEEDBACK_STATUSES = {"Open", "Triaged", "Planned", "Done", "Rejected"}
VALID_HUMAN_INDEX_STATUSES = {"Open", "Reviewed", "Extracted", "Archived"}
VALID_KNOWLEDGE_STATUSES = {"Draft", "Active", "Promoted", "Stale", "Rejected"}
VALID_SUBTASK_STATUSES = {"Pending", "Active", "Done", "Blocked", "Skipped", "Superseded"}
VALID_TASK_STATUSES = {"Active", "Paused", "Done", "Empty"}
VALID_SOURCE_STATUSES = {"To Read", "Reading", "Read", "Useful", "Archived", "Rejected"}
VALID_HUMAN_NOTE_STATUSES = {"Open", "Triaged", "Done", "Rejected"}
VALID_MERGE_RESOLUTIONS = {"merged", "rejected", "no_merge_required", "archived"}
VALID_WORKSTREAM_ATTENTION = {"Now", "Next", "Waiting", "Retained"}
VALID_WORKSTREAM_STATUSES = {"Proposed", "Open", "Active", "Blocked", "ReadyToMerge", "Merging", "Done", "Cancelled"}
VALID_WORKSTREAM_TYPES = {"Task", "Merge", "Maintenance"}
