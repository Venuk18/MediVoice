from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.hospital import HospitalRead, HospitalDetailRead
from app.services import doctor_service

router = APIRouter(prefix="/hospitals", tags=["Hospitals"])


@router.get("", response_model=List[HospitalRead], summary="List hospitals")
def list_hospitals(db: Session = Depends(get_db)):
    """Retrieve all operational hospital entities."""
    return doctor_service.get_hospitals(db)


@router.get("/{hospital_id}", response_model=HospitalDetailRead, summary="Get hospital by ID")
def get_hospital(hospital_id: str, db: Session = Depends(get_db)):
    """Retrieve hospital details including all active clinical departments."""
    hospital = doctor_service.get_hospital_by_id(db, hospital_id)
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with ID '{hospital_id}' not found.",
        )
    return hospital
