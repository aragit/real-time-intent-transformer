from fastapi import APIRouter, HTTPException

from src.memory.customer_profile import CustomerProfileStore
from src.models.customer import CustomerProfile

router = APIRouter()
store = CustomerProfileStore()


@router.get("/customers/{customer_id}/profile", response_model=CustomerProfile)
async def get_profile(customer_id: str):
    """Get aggregated customer behavior profile."""
    profile = store.get(customer_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Customer not found")
    return profile
