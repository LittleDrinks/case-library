"""检索目录场景步骤。

目录替身记录检索请求，断言用户可观察响应与权限域。
"""
from pytest_bdd import given, parsers, then, when

from app.modules.search.meilisearch import (
    CatalogMetadata,
    CatalogPage,
    CatalogRequest,
    Principal,
    SearchUnavailable,
)


class RecordingCatalog:
    def __init__(self) -> None:
        self.requests: list[CatalogRequest] = []
        self.unavailable = False

    def health(self, *_args) -> None:
        if self.unavailable:
            raise SearchUnavailable("检索目录正在同步")

    def search(self, request) -> CatalogPage:
        self.requests.append(request)
        metadata = None
        if request.include_metadata:
            metadata = CatalogMetadata(
                0, {"all": 0, "case": 0, "knowledge": 0, "material": 0}, {}
            )
        return CatalogPage([], metadata, True, request.offset > 0)


def _install(ctx) -> RecordingCatalog:
    catalog = RecordingCatalog()
    ctx["client"].app.state.search_catalog = catalog
    ctx["memo"]["catalog"] = catalog
    return catalog
@when(parsers.parse('教师以"{mode}"模式检索带两个标签的案例'))
def teacher_searches_with_tags(ctx, mode):
    _install(ctx)
    tag_mode = {"任意": "any", "全部": "all"}[mode]
    ctx["client"].post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    ctx["memo"]["last_response"] = ctx["client"].get(
        "/api/search",
        params={"kind": "case", "tagMode": tag_mode,
                "tagIds": ["tag-seed-4-1", "tag-seed-4-2"]},
    )
    assert ctx["memo"]["last_response"].status_code == 200, \
        ctx["memo"]["last_response"].text


@then(parsers.parse('检索条件为"{op}"且请求成功'))
def condition_is(ctx, op):
    catalog = ctx["memo"]["catalog"]
    request = catalog.requests[0]
    assert request.tag_condition.op == {"或": "or", "且": "and"}[op]


@when("教师以未知标签检索")
def search_unknown_tag(ctx):
    _install(ctx)
    ctx["client"].post("/api/auth/login", json={"username": "user", "password": "user123"})
    ctx["memo"]["last_response"] = ctx["client"].get(
        "/api/search", params={"kind": "case", "tagIds": ["tag-missing"]}
    )


@given("检索目录处于同步中")
def catalog_unavailable(ctx):
    catalog = _install(ctx)
    catalog.unavailable = True
    ctx["client"].post("/api/auth/login", json={"username": "user", "password": "user123"})



@when("教师发起检索")
def teacher_searches(ctx):
    ctx["memo"]["last_response"] = ctx["client"].get("/api/search")


@when("未登录访客发起检索")
def anonymous_searches(ctx):
    _install(ctx)
    ctx["client"].cookies.clear()
    ctx["memo"]["last_response"] = ctx["client"].get("/api/search")


@then("检索请求携带匿名权限域")
def anonymous_scope_asserted(ctx):
    catalog = ctx["memo"]["catalog"]
    assert ctx["memo"]["last_response"].status_code == 200
    assert catalog.requests, "目录未收到检索请求"
    assert catalog.requests[0].principal == Principal(None, "anonymous")
