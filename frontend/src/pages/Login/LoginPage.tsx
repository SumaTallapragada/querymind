import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, LogIn } from "lucide-react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
} from "@/components/ui";
import { useLogin } from "@/hooks/useAuth";
import { useAuthStore } from "@/store/authStore";
import { errorMessage } from "@/utils/errors";

const loginSchema = z.object({
  username: z.string().trim().min(1, "Enter your username."),
  password: z.string().min(1, "Enter your password."),
});

type LoginFormValues = z.infer<typeof loginSchema>;

interface LocationState {
  from?: string;
}

export function LoginPage() {
  const status = useAuthStore((state) => state.status);
  const navigate = useNavigate();
  const location = useLocation();
  const login = useLogin();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: "", password: "" },
  });

  if (status === "authenticated") {
    const from = (location.state as LocationState | null)?.from ?? "/";
    return <Navigate to={from} replace />;
  }

  const onSubmit = handleSubmit((values) => {
    if (login.isPending) return;
    login.mutate(values, {
      onSuccess: () => {
        const from = (location.state as LocationState | null)?.from ?? "/";
        navigate(from, { replace: true });
      },
    });
  });

  return (
    <div className="flex min-h-svh items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Sign in to QueryMind</CardTitle>
          <CardDescription>Enter your username and password to continue.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4" aria-label="Sign in">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="login-username">Username</Label>
              <Input
                id="login-username"
                autoComplete="username"
                aria-invalid={errors.username ? "true" : "false"}
                aria-describedby={errors.username ? "login-username-error" : undefined}
                {...register("username")}
              />
              {errors.username && (
                <p id="login-username-error" role="alert" className="text-sm text-destructive">
                  {errors.username.message}
                </p>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="login-password">Password</Label>
              <Input
                id="login-password"
                type="password"
                autoComplete="current-password"
                aria-invalid={errors.password ? "true" : "false"}
                aria-describedby={errors.password ? "login-password-error" : undefined}
                {...register("password")}
              />
              {errors.password && (
                <p id="login-password-error" role="alert" className="text-sm text-destructive">
                  {errors.password.message}
                </p>
              )}
            </div>

            {login.isError && (
              <p role="alert" className="text-sm text-destructive">
                {errorMessage(login.error)}
              </p>
            )}

            <Button type="submit" disabled={login.isPending} className="mt-1">
              {login.isPending ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : (
                <LogIn aria-hidden="true" />
              )}
              {login.isPending ? "Signing in..." : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}