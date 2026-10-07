import { readFileSync } from "node:fs";

export default class RealAiSafeReporter {
  onEnd(result) {
    let report = {};
    try {
      report = JSON.parse(readFileSync(process.env.REAL_AI_REPORT_PATH, "utf8"));
    } catch {
      report = {
        sourceHash: process.env.REAL_AI_SOURCE_HASH || null,
        verified: [],
        failed: [{ stage: "report", code: "report_unavailable" }],
        notRun: ["real_ai_account_flow"],
      };
    }
    process.stdout.write(`${JSON.stringify({
      status: result.status,
      sourceHash: report.sourceHash || null,
      runtimeBuild: report.runtimeBuild || {},
      syntheticIds: report.syntheticIds || {},
      model: report.model || null,
      resultSummary: report.resultSummary || {},
      testStatus: report.testStatus || "not_run",
      verified: report.verified || [],
      failed: report.failed || [],
      notRun: report.notRun || [],
      permissions: report.permissions || {},
      runStatus: report.runStatus || null,
      cleanup: report.cleanup || "not_run",
    })}\n`);
  }
}
