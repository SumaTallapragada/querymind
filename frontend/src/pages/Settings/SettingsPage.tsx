import type { ReactNode } from "react";
import { AlertCircle } from "lucide-react";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui";
import { LoadingIndicator } from "@/components/LoadingIndicator";
import { useSettings } from "@/hooks/useSettings";
import { errorMessage } from "@/utils/errors";

function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2.5 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  );
}

export function SettingsPage() {
  const { data, isLoading, isError, error } = useSettings();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Settings</CardTitle>
        <CardDescription>
          Read-only application configuration from GET /settings. Never includes credentials.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && <LoadingIndicator label="Loading settings..." />}

        {isError && (
          <div role="alert" className="flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            {errorMessage(error)}
          </div>
        )}

        {data && (
          <dl className="flex flex-col">
            <InfoRow label="Application" value={data.app_name} />
            <InfoRow label="Version" value={<Badge variant="secondary">{data.version}</Badge>} />
            <InfoRow label="Environment" value={<span className="capitalize">{data.environment}</span>} />
            <InfoRow label="API prefix" value={<code className="font-mono text-xs">{data.api_v1_prefix}</code>} />
            <InfoRow label="Database engine" value={data.database_engine} />
            <InfoRow label="Database name" value={data.database_name} />
            <InfoRow label="LLM provider" value={<span className="capitalize">{data.llm_provider}</span>} />
            <InfoRow label="LLM model" value={data.llm_model} />
            <InfoRow
              label="Streaming transports"
              value={
                <div className="flex gap-1.5">
                  {data.streaming_transports.map((transport) => (
                    <Badge key={transport} variant="outline" className="uppercase">
                      {transport}
                    </Badge>
                  ))}
                </div>
              }
            />
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
