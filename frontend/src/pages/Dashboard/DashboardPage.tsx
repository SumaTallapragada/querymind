import { AlertCircle } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui";
import { QueryInput } from "@/components/QueryInput";
import { QueryHistory } from "@/components/QueryHistory";
import { PipelineTimeline } from "@/components/PipelineTimeline";
import { StreamingEvents } from "@/components/StreamingEvents";
import { SQLViewer } from "@/components/SQLViewer";
import { ValidationPanel } from "@/components/ValidationPanel";
import { RepairPanel } from "@/components/RepairPanel";
import { ExecutionPanel } from "@/components/ExecutionPanel";
import { AnswerCard } from "@/components/AnswerCard";
import { ResultTable } from "@/components/ResultTable";
import { useQueryStore } from "@/store/queryStore";
import { deriveStageRowsFromEvents, deriveStageRowsFromTimings } from "@/utils/pipelineTimeline";

export function DashboardPage() {
  const mode = useQueryStore((state) => state.mode);
  const status = useQueryStore((state) => state.status);
  const events = useQueryStore((state) => state.events);
  const response = useQueryStore((state) => state.response);
  const errorMessage = useQueryStore((state) => state.errorMessage);

  const isStreamingSession = mode === "streaming" && (status === "running" || events.length > 0);
  const timelineRows = isStreamingSession
    ? deriveStageRowsFromEvents(events, status !== "running")
    : response
      ? deriveStageRowsFromTimings(response.statistics.stage_timings)
      : [];

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[380px_1fr]">
      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Ask a question</CardTitle>
            <CardDescription>Runs the complete QueryMind pipeline end to end.</CardDescription>
          </CardHeader>
          <CardContent>
            <QueryInput />
          </CardContent>
        </Card>

        {timelineRows.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Pipeline timeline</CardTitle>
              <CardDescription>Status and latency per stage.</CardDescription>
            </CardHeader>
            <CardContent>
              <PipelineTimeline rows={timelineRows} />
            </CardContent>
          </Card>
        )}

        {isStreamingSession && (
          <Card>
            <CardHeader>
              <CardTitle>Streaming events</CardTitle>
              <CardDescription>Live event feed from the backend.</CardDescription>
            </CardHeader>
            <CardContent>
              <StreamingEvents events={events} />
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle>History</CardTitle>
            <CardDescription>Questions asked this session.</CardDescription>
          </CardHeader>
          <CardContent>
            <QueryHistory />
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-col gap-4">
        {errorMessage && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
            <p>{errorMessage}</p>
          </div>
        )}

        {response && (
          <Card>
            <CardHeader>
              <CardTitle>Request metadata</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
                <div>
                  <dt className="text-xs text-muted-foreground">Status</dt>
                  <dd className="capitalize">{response.status}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Total latency</dt>
                  <dd>{response.statistics.total_latency_ms.toFixed(1)} ms</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Repair</dt>
                  <dd>
                    {response.statistics.repair_attempted
                      ? response.statistics.repair_performed
                        ? "Attempted, succeeded"
                        : "Attempted, did not succeed"
                      : "Not needed"}
                  </dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Answer</CardTitle>
          </CardHeader>
          <CardContent>
            <AnswerCard businessAnswer={response?.business_answer ?? null} />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-5">
            <Tabs defaultValue="sql">
              <TabsList>
                <TabsTrigger value="sql">SQL</TabsTrigger>
                <TabsTrigger value="validation">Validation</TabsTrigger>
                <TabsTrigger value="repair">Repair</TabsTrigger>
                <TabsTrigger value="execution">Execution</TabsTrigger>
                <TabsTrigger value="result">Result</TabsTrigger>
              </TabsList>
              <TabsContent value="sql">
                <SQLViewer
                  sql={response?.business_answer?.execution_result.executed_sql ?? response?.generated_sql?.sql ?? null}
                  validationResult={response?.validation_result ?? null}
                  repairResult={response?.repair_result ?? null}
                />
              </TabsContent>
              <TabsContent value="validation">
                <ValidationPanel validationResult={response?.validation_result ?? null} />
              </TabsContent>
              <TabsContent value="repair">
                <RepairPanel repairResult={response?.repair_result ?? null} />
              </TabsContent>
              <TabsContent value="execution">
                <ExecutionPanel executionResult={response?.execution_result ?? null} />
              </TabsContent>
              <TabsContent value="result">
                <ResultTable table={response?.business_answer?.formatted_table ?? null} />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
