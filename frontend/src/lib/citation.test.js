import { expect, it } from "vitest";
import {
  caseVersionUrl, citationNumberMap, collectCitationKeys, sourceKey,
} from "./citation.js";

const sources = [
  { id: "src-b", sourceType: "case", caseId: "case-2", versionId: "ver-2", title: "乙案例" },
  { id: "src-a", sourceType: "case", caseId: "case-1", versionId: "ver-1", title: "甲案例" },
];

function citedDocument(marks) {
  return {
    type: "doc",
    content: [{
      type: "paragraph",
      content: [{ type: "text", text: "正文", marks }],
    }],
  };
}

it("按资料区保留顺序为全部来源固定编号", () => {
  const map = citationNumberMap(sources);
  expect(map.get("case:src-b")).toBe(1);
  expect(map.get("case:src-a")).toBe(2);
  expect(citationNumberMap([]).size).toBe(0);
});

it("按出现顺序收集去重后的引用键", () => {
  const document = {
    type: "doc",
    content: [
      citedDocument([{ type: "citation", attrs: { sourceType: "case", sourceId: "src-a" } }]),
      citedDocument([
        { type: "bold" },
        { type: "citation", attrs: { sourceType: "case", sourceId: "src-b" } },
      ]),
      citedDocument([{ type: "citation", attrs: { sourceType: "case", sourceId: "src-a" } }]),
    ],
  };
  expect(collectCitationKeys(document)).toEqual(["case:src-a", "case:src-b"]);
});

it("sourceKey 与引用 attrs 键一致", () => {
  expect(sourceKey(sources[0])).toBe("case:src-b");
});

it("来源链接固定到已发布版本", () => {
  expect(caseVersionUrl(sources[0])).toBe("#/cases/case-2?versionId=ver-2");
  expect(caseVersionUrl({ caseId: "case/3" })).toBe("#/cases/case%2F3");
});
