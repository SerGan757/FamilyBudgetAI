from .start import router as start_router
from .menu import router as menu_router
from .expenses import router as expenses_router
from .history import router as history_router
from .statistics import router as statistics_router
from .delete import router as delete_router

routers = (
    start_router,
    menu_router,
    history_router,
    statistics_router,
    delete_router,
    expenses_router,
)