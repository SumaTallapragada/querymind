import type { ReactNode } from "react";
import { ShieldAlert } from "lucide-react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui";
import { useAuthStore } from "@/store/authStore";
import { roleSatisfies } from "@/utils/roles";
import type { UserRole } from "@/models";

export interface RequireRoleProps {
  minRole: UserRole;
  children: ReactNode;
}

/**
 * Page-level role gate, nested inside `RequireAuth` (so a `user` is always expected to exist by
 * the time this renders). UX/access-control assistance only -- the backend re-checks every
 * request via `RequireAdmin`/`RequireAnalyst` regardless of what this renders, so a mismatch
 * here shows an explanatory message rather than a redirect loop against routes the caller's role
 * may not satisfy either.
 */
export function RequireRole({ minRole, children }: RequireRoleProps) {
  const role = useAuthStore((state) => state.user?.role);

  if (!role || !roleSatisfies(role, minRole)) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-destructive" aria-hidden="true" />
            Access restricted
          </CardTitle>
          <CardDescription>
            Your account role does not have access to this page. Contact an administrator if you
            believe this is a mistake.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return <>{children}</>;
}