export const caseUnavailableMessage = "案例不可访问";
export const caseUnavailableNotice = "case-unavailable";

export async function resolveWorkbenchAccess(caseId, user, getCase) {
  try {
    const caseRecord = await getCase(caseId);
    if (caseRecord.ownerId === user.id) return null;
    return user.role === "admin" ? reviewRoute(caseId) : publicRoute(caseId);
  } catch (error) {
    if (error.status !== 404) throw error;
    return unavailableRoute();
  }
}

function publicRoute(caseId) {
  return { name: "case-public", params: { id: caseId }, replace: true };
}

function reviewRoute(caseId) {
  return { name: "case-review", params: { id: caseId }, replace: true };
}

function unavailableRoute() {
  return {
    name: "my-cases", query: { notice: caseUnavailableNotice }, replace: true,
  };
}
