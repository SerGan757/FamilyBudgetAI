from .admin import router as admin_router
from .start import router as start_router
from .registration import router as registration_router
from .menu import router as menu_router
from .expenses import router as expenses_router
from .history import router as history_router
from .statistics import router as statistics_router
from .delete import router as delete_router
from .recurring import router as recurring_router
from .settings import router as settings_router
from .projects import router as projects_router
from .savings_goal import router as savings_goal_router
from .categories import router as categories_router
from .year_analytics import router as year_analytics_router


routers = (
    admin_router,
    start_router,
    registration_router,
    recurring_router,
    delete_router,
    menu_router,
    year_analytics_router,
    history_router,
    statistics_router,
    projects_router,
    savings_goal_router,
    categories_router,
    settings_router,
    expenses_router,
)
