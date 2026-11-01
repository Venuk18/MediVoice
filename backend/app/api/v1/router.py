
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.hospitals import router as hospitals_router
from app.api.v1.doctors import router as doctors_router
from app.api.v1.appointments import router as appointments_router
from app.api.v1.lab_orders import router as lab_orders_router
from app.api.v1.insurance import router as insurance_router
from app.api.v1.maintenance import router as maintenance_router
from app.api.v1.workflow import router as workflow_router
from app.api.v1.agent import router as agent_router
from app.api.v1.voice import router as voice_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(hospitals_router)
api_router.include_router(doctors_router)
api_router.include_router(appointments_router)
api_router.include_router(lab_orders_router)
api_router.include_router(insurance_router)
api_router.include_router(maintenance_router)
api_router.include_router(workflow_router)
api_router.include_router(agent_router)
api_router.include_router(voice_router)


