import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.BASE_URL || "http://frontend";
const idleSeconds = Number(__ENV.KEEPALIVE_IDLE_SECONDS || 6);
const reuseCycles = Number(__ENV.KEEPALIVE_REUSE_CYCLES || 1);
const probe = __ENV.KEEPALIVE_PROBE || "upstream-keepalive";
const vus = Number(__ENV.KEEPALIVE_VUS || 1000);

export const options = {
  scenarios: {
    idleReuse: {
      executor: "per-vu-iterations",
      vus,
      iterations: 1,
      maxDuration: "20s",
    },
  },
  discardResponseBodies: true,
  thresholds: {
    checks: ["rate==1"],
    http_req_failed: ["rate==0"],
  },
};

function request(phase) {
  const response = http.get(`${baseUrl}/api/constants?probe=${probe}&phase=${phase}`);
  check(response, { [`${phase} succeeds`]: (result) => result.status === 200 });
}

export default function () {
  request("prime");
  for (let cycle = 1; cycle <= reuseCycles; cycle += 1) {
    sleep(idleSeconds);
    request(`reuse-${cycle}`);
  }
}
