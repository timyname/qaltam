from enum import Enum


class AccountType(str, Enum):
    PERSONAL = "personal"
    BUSINESS = "business"


class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


class RoleTag(str, Enum):
    CFO = "CFO"
    CMO = "CMO"
    COO = "COO"
    CEO = "CEO"


class WorkspaceRole(str, Enum):
    OWNER = "owner"
    CFO = "cfo"
    COO = "coo"
    CASHIER = "cashier"
    FAMILY_MEMBER = "family_member"


class ObligationPriority(str, Enum):
    CRITICAL = "1_critical"
    REGULAR = "2_regular"


class HypothesisStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ClientMode(str, Enum):
    PERSONAL = "personal"
    BUSINESS = "business"
    MIXED = "mixed"
