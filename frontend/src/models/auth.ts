/** Mirrors `querymind.auth.schemas` / `querymind.auth.models.UserRole` -- the `/auth/*` request
 * and response shapes. `password_hash` never appears here, matching `UserRead` on the backend.
 */

export type UserRole = "admin" | "analyst" | "viewer";

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserRead {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  role: UserRole;
  created_at: string;
  updated_at: string;
}