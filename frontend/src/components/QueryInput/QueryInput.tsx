import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, Send, Square } from "lucide-react";
import {
  Button,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Tabs,
  TabsList,
  TabsTrigger,
  Textarea,
} from "@/components/ui";
import { useAskQuestion } from "@/hooks/useQuery";
import { useStreaming } from "@/hooks/useStreaming";
import { useQueryStore, type QueryMode } from "@/store/queryStore";
import { useUiStore } from "@/store/uiStore";
import type { StreamingTransport } from "@/models";

const questionSchema = z.object({
  question: z
    .string()
    .trim()
    .min(1, "Enter a question.")
    .max(2000, "Keep the question under 2000 characters."),
});

type QuestionFormValues = z.infer<typeof questionSchema>;

const EXAMPLE_QUESTIONS = [
  "Who are our top 5 customers by revenue?",
  "What is the average order value this year?",
  "Which products have the highest return rate?",
];

export function QueryInput() {
  const status = useQueryStore((state) => state.status);
  const mode = useQueryStore((state) => state.mode);
  const setMode = useQueryStore((state) => state.setMode);
  const transport = useUiStore((state) => state.streamingTransport);
  const setTransport = useUiStore((state) => state.setStreamingTransport);
  const askQuestion = useAskQuestion();
  const { start, stop } = useStreaming();

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<QuestionFormValues>({
    resolver: zodResolver(questionSchema),
    defaultValues: { question: "" },
  });

  const isRunning = status === "running";

  const onSubmit = handleSubmit((values) => {
    if (mode === "direct") {
      askQuestion.mutate(values.question);
    } else {
      start(values.question);
    }
  });

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" aria-label="Ask QueryMind a question">
      <Tabs value={mode} onValueChange={(value) => setMode(value as QueryMode)}>
        <TabsList>
          <TabsTrigger value="direct">Direct (POST /query)</TabsTrigger>
          <TabsTrigger value="streaming">Streaming</TabsTrigger>
        </TabsList>
      </Tabs>

      {mode === "streaming" && (
        <div className="flex items-center gap-2">
          <Label htmlFor="transport-select" className="text-muted-foreground">
            Transport
          </Label>
          <Select
            value={transport}
            onValueChange={(value) => setTransport(value as StreamingTransport)}
          >
            <SelectTrigger id="transport-select" className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="sse">Server-Sent Events</SelectItem>
              <SelectItem value="websocket">WebSocket</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="question-input">Question</Label>
        <Textarea
          id="question-input"
          rows={3}
          placeholder="Ask a natural language question about your data..."
          aria-invalid={errors.question ? "true" : "false"}
          aria-describedby={errors.question ? "question-error" : undefined}
          {...register("question")}
        />
        {errors.question && (
          <p id="question-error" role="alert" className="text-sm text-destructive">
            {errors.question.message}
          </p>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {EXAMPLE_QUESTIONS.map((example) => (
          <Button
            key={example}
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setValue("question", example, { shouldValidate: true })}
          >
            {example}
          </Button>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={isRunning}>
          {isRunning ? (
            <Loader2 className="animate-spin" aria-hidden="true" />
          ) : (
            <Send aria-hidden="true" />
          )}
          {isRunning ? "Running..." : "Ask QueryMind"}
        </Button>
        {isRunning && mode === "streaming" && (
          <Button type="button" variant="outline" onClick={stop}>
            <Square aria-hidden="true" />
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}
