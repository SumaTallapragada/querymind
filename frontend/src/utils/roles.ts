/** Mirrors the rank `AuthenticationService.require_role` uses server-side (`querymind.auth.models
 * .UserRole`'s own docstring): `ADMIN` > `ANALYST` > `VIEWER`, and a higher role satisfies a
 * lower requirement. Frontend-only, for hiding nav/routes a role can't use -- never the security
 * boundary itself; the backend re-checks every request regardless of what this says.
 */

import type { UserRole } from "@/models";

const ROLE_RANK: Record<UserRole, number> = {
  viewer: 0,
  analyst: 1,
  admin: 2,
};

export function roleSatisfies(userRole: UserRole, minRole: UserRole): boolean {
  return ROLE_RANK[userRole] >= ROLE_RANK[minRole];
}