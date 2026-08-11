import { LogOut, Menu, Moon, Sun, SunMoon } from "lucide-react";
import { Badge, Button } from "@/components/ui";
import { useUiStore, type Theme } from "@/store/uiStore";
import { useAuthStore } from "@/store/authStore";

const THEME_CYCLE: Record<Theme, Theme> = {
  light: "dark",
  dark: "system",
  system: "light",
};

const THEME_ICON: Record<Theme, typeof Sun> = {
  light: Sun,
  dark: Moon,
  system: SunMoon,
};

export interface TopbarProps {
  title: string;
}

export function Topbar({ title }: TopbarProps) {
  const theme = useUiStore((state) => state.theme);
  const setTheme = useUiStore((state) => state.setTheme);
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const ThemeIcon = THEME_ICON[theme];

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-background px-4 lg:px-6">
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          aria-label="Open navigation"
          onClick={toggleSidebar}
        >
          <Menu className="h-4 w-4" />
        </Button>
        <h1 className="text-base font-semibold tracking-tight">{title}</h1>
      </div>
      <div className="flex items-center gap-2">
        {user && (
          <div className="hidden items-center gap-2 sm:flex">
            <span className="text-sm font-medium">{user.username}</span>
            <Badge variant="secondary" className="capitalize">
              {user.role}
            </Badge>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Theme: ${theme}. Activate to switch.`}
          title={`Theme: ${theme}`}
          onClick={() => setTheme(THEME_CYCLE[theme])}
        >
          <ThemeIcon className="h-4 w-4" />
        </Button>
        {user && (
          <Button variant="ghost" size="icon" aria-label="Log out" title="Log out" onClick={() => void logout()}>
            <LogOut className="h-4 w-4" />
          </Button>
        )}
      </div>
    </header>
  );
}
