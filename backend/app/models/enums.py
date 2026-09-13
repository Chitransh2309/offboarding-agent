import enum


class SystemType(str, enum.Enum):
    GITHUB = "github"
    SLACK = "slack"
    NOTION = "notion"
    LINEAR = "linear"


class EnvironmentType(str, enum.Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class ConnectionStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    INVALID = "invalid"


class EmployeeStatus(str, enum.Enum):
    ACTIVE = "active"
    DEPARTING = "departing"
    OFFBOARDED = "offboarded"


class GrantStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    REVOKE_FAILED = "revoke_failed"


class WorkItemStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    CLOSED = "closed"


class RunStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class ActionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class VerifyStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    STILL_PRESENT = "still_present"
    ERROR = "error"


class SuggestedBy(str, enum.Enum):
    LLM = "llm"
    HUMAN = "human"
