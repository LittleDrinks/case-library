import { beforeEach, expect, test } from "vitest";
import { rememberMaterialReturn, restoreMaterialReturn } from "./materialNavigation.js";

beforeEach(() => sessionStorage.clear());

test("恢复匹配查询的素材目录状态并消费会话记录", () => {
  const query = { caseId: "case-1", q: "科学家" };
  rememberMaterialReturn(query, { cursor: "signed-token", page: 2, total: 76 });

  expect(restoreMaterialReturn({ q: "科学家", caseId: "case-1" })).toMatchObject({
    cursor: "signed-token", page: 2, total: 76,
  });
  expect(sessionStorage.getItem("case-library:material-return")).toBeNull();
});

test("查询变化时不恢复旧目录状态", () => {
  rememberMaterialReturn({ caseId: "case-1" }, { cursor: "signed-token" });

  expect(restoreMaterialReturn({ caseId: "case-2" })).toBeNull();
  expect(sessionStorage.getItem("case-library:material-return")).toBeNull();
});
