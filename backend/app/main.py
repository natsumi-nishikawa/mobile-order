from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.customer_sessions import router as customer_sessions_router
from app.routers.customer_participants import router as customer_participants_router
from app.routers.customer_menu import router as customer_menu_router
from app.routers.customer_selections import router as customer_selections_router
from app.routers.customer_orders import router as customer_orders_router
from app.routers.customer_billing import router as customer_billing_router
from app.routers.admin_products import router as admin_products_router
from app.routers.admin_categories import router as admin_categories_router
from app.routers.admin_tables import router as admin_tables_router
from app.routers.admin_business_hours import router as admin_business_hours_router
from app.routers.admin_accounting import router as admin_accounting_router


app = FastAPI()


# ReactからFastAPIへの通信を許可
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(customer_sessions_router)
app.include_router(customer_participants_router)
app.include_router(customer_menu_router)
app.include_router(customer_selections_router)
app.include_router(customer_orders_router)
app.include_router(customer_billing_router)
app.include_router(admin_products_router)
app.include_router(admin_categories_router)
app.include_router(admin_tables_router)
app.include_router(admin_business_hours_router)
app.include_router(admin_accounting_router)


@app.get("/")
def root():
    return {"message": "Mobile Order API"}
