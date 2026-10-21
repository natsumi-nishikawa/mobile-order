from app.demo_auth import require_demo_csrf, require_demo_session
from app.main import app
from app.store_auth import require_admin, require_staff
from fastapi.routing import APIRoute

PROTECTED_PREFIXES = ("/api/customer", "/api/staff", "/api/admin")
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def dependency_calls(route: APIRoute):
    return {dependency.call for dependency in route.dependant.dependencies}


def registered_http_routes():
    for registered in app.routes:
        if isinstance(registered, APIRoute):
            yield registered
            continue
        included_router = getattr(registered, "original_router", None)
        if included_router is not None:
            yield from (
                route for route in included_router.routes if isinstance(route, APIRoute)
            )


def test_all_customer_staff_and_admin_http_routes_require_demo_session():
    protected_routes = [
        route
        for route in registered_http_routes()
        if route.path.startswith(PROTECTED_PREFIXES)
    ]
    assert protected_routes
    for route in protected_routes:
        assert require_demo_session in dependency_calls(route), route.path


def test_all_cookie_authenticated_mutations_require_csrf():
    mutation_routes = [
        route
        for route in registered_http_routes()
        if route.path.startswith(PROTECTED_PREFIXES)
        and route.methods.intersection(MUTATING_METHODS)
    ]
    assert mutation_routes
    for route in mutation_routes:
        assert require_demo_csrf in dependency_calls(route), route.path


def test_staff_and_admin_routes_keep_cognito_role_dependencies():
    for route in registered_http_routes():
        calls = dependency_calls(route)
        if route.path.startswith("/api/staff"):
            assert require_staff in calls, route.path
        elif route.path.startswith("/api/admin"):
            assert require_admin in calls, route.path
