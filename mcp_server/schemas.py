from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class TransactionDetailsInput(BaseModel):
    transaction_id: str = Field(description="Unique transaction identifier (e.g. TX-001)")

class TransactionDetailsOutput(BaseModel):
    transaction_id: str
    customer_id: str
    masked_pan: str
    merchant: str
    amount: float
    currency: str
    timestamp: str
    country: str
    status: str

class CustomerDisputeHistoryInput(BaseModel):
    customer_id: str = Field(description="Customer identifier (e.g. CUST-001)")

class CustomerDisputeHistoryOutput(BaseModel):
    customer_id: str
    total_prior_disputes: int
    open_disputes: int
    prior_fraud_reports: int
    win_rate: float
    tenure_months: int

class ErrorOutput(BaseModel):
    error: str
    message: str
    code: int
