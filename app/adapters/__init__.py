"""Importing this package registers every adapter in ADAPTERS."""

from app.adapters import eightfold, greenhouse, lever, oracle_hcm, workday  # noqa: F401
from app.adapters.company import (  # noqa: F401
    amazon,
    amd,
    apple,
    atlassian,
    barclays,
    capgemini,
    google,
    ibm,
    phonepe,
    swiggy,
    zerodha,
)
