from fastapi import APIRouter

from app.api.operations import router as operations_router
from app.modules.annotations.routes import router as annotations_router
from app.modules.ai.routes import admin_router as admin_ai_router
from app.modules.ai.routes import router as ai_router
from app.modules.agent.routes import router as agent_router
from app.modules.auth.routes import router as auth_router
from app.modules.attachments.routes import router as attachments_router
from app.modules.cases.routes import router as cases_router
from app.modules.cases.ai_routes import router as case_ai_router
from app.modules.case_materials.routes import router as case_materials_router
from app.modules.materials.routes import candidate_router as material_candidates_router
from app.modules.materials.routes import content_router as material_content_router
from app.modules.materials.routes import router as materials_router
from app.modules.search.routes import router as search_router
from app.modules.search.ai_routes import router as search_ai_router

router = APIRouter()
router.include_router(operations_router)
router.include_router(auth_router)
router.include_router(agent_router)
router.include_router(ai_router)
router.include_router(admin_ai_router)
router.include_router(cases_router)
router.include_router(case_ai_router)
router.include_router(case_materials_router)
router.include_router(attachments_router)
router.include_router(annotations_router)
router.include_router(materials_router)
router.include_router(material_candidates_router)
router.include_router(material_content_router)
router.include_router(search_router)
router.include_router(search_ai_router)
