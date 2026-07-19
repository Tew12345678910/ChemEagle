"use client";

import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Beaker,
  CheckCircle2,
  Clipboard,
  Download,
  ExternalLink,
  FileImage,
  FileText,
  GitFork,
  Link2,
  RotateCcw,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  displayChemical,
  displaySmiles,
  errorMessage,
  getReactions,
  getResultCount,
  getStatus,
  getTaskId,
  type JsonRecord,
  type Reaction,
} from "@/lib/chemeagle";

type InputMode = "image" | "pdf" | "url";
type RunState = "idle" | "submitting" | "queued" | "completed" | "error";

const FILE_ACCEPT: Record<Exclude<InputMode, "url">, string> = {
  image: "image/png,image/jpeg,image/webp,image/tiff",
  pdf: "application/pdf",
};

function prettyJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function reactionEquation(reaction: Reaction) {
  const reactants = reaction.reactants.map(displayChemical).join(" + ");
  const products = reaction.products.map(displayChemical).join(" + ");
  if (!reactants && !products) return null;
  return `${reactants || "Unknown reactant"} → ${products || "Unknown product"}`;
}

function ChemicalList({ title, items }: { title: string; items: JsonRecord[] }) {
  if (items.length === 0) return null;

  return (
    <section className="flex flex-col gap-2">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      <div className="flex flex-col gap-2">
        {items.map((item, index) => {
          const smiles = displaySmiles(item);
          return (
            <div
              className="flex min-w-0 flex-col gap-1 rounded-lg border bg-muted/40 p-3"
              key={`${title}-${index}-${displayChemical(item)}`}
            >
              <span className="font-medium">{displayChemical(item)}</span>
              {smiles ? (
                <code className="overflow-x-auto text-xs text-muted-foreground">
                  {smiles}
                </code>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ReactionCard({ reaction }: { reaction: Reaction }) {
  const equation = reactionEquation(reaction);

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Reaction {reaction.id}</CardTitle>
        <CardDescription>
          {equation || "Structured extraction returned by ChemEAGLE"}
        </CardDescription>
        <CardAction>
          <Badge variant="secondary">Structured</Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {reaction.smiles ? (
          <section className="flex flex-col gap-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Reaction SMILES
            </p>
            <code className="overflow-x-auto rounded-lg bg-muted p-3 text-xs">
              {reaction.smiles}
            </code>
          </section>
        ) : null}
        <div className="grid gap-4 lg:grid-cols-2">
          <ChemicalList title="Reactants" items={reaction.reactants} />
          <ChemicalList title="Products" items={reaction.products} />
        </div>
        <ChemicalList title="Conditions" items={reaction.conditions} />
      </CardContent>
    </Card>
  );
}

function SourcePreview({ file, previewUrl }: { file: File; previewUrl: string }) {
  if (file.type === "application/pdf") {
    return (
      <object
        aria-label={`Preview of ${file.name}`}
        className="h-full min-h-96 w-full rounded-lg border bg-muted"
        data={previewUrl}
        type="application/pdf"
      >
        <p className="p-4 text-sm text-muted-foreground">
          This browser cannot preview the PDF. The file is still ready to process.
        </p>
      </object>
    );
  }

  return (
    <div className="relative min-h-96 overflow-hidden rounded-lg border bg-muted">
      <Image
        alt={`Preview of ${file.name}`}
        className="object-contain p-4"
        fill
        sizes="(max-width: 1024px) 100vw, 50vw"
        src={previewUrl}
        unoptimized
      />
    </div>
  );
}

export function ExtractionWorkbench() {
  const [inputMode, setInputMode] = useState<InputMode>("image");
  const [urlKind, setUrlKind] = useState<"image" | "pdf">("pdf");
  const [file, setFile] = useState<File | null>(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [runState, setRunState] = useState<RunState>("idle");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [result, setResult] = useState<unknown>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const previewUrl = useMemo(
    () => (file ? URL.createObjectURL(file) : null),
    [file],
  );
  const reactions = useMemo(() => getReactions(result), [result]);
  const resultCount = useMemo(() => getResultCount(result), [result]);
  const isRunning = runState === "submitting" || runState === "queued";
  const canSubmit = inputMode === "url" ? sourceUrl.trim().length > 0 : Boolean(file);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;
    let timeout: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const response = await fetch(
          `/api/chemeagle/status/${encodeURIComponent(taskId)}`,
          { cache: "no-store" },
        );
        const payload = (await response.json()) as unknown;
        if (!response.ok) throw new Error(errorMessage(payload, "Status check failed."));
        if (cancelled) return;

        const status = getStatus(payload)?.toLowerCase();
        if (status === "completed" || status === "complete" || status === "success") {
          setResult(payload);
          setRunState("completed");
          setTaskId(null);
          toast.success("Extraction complete");
          return;
        }
        if (status === "error" || status === "failed" || status === "failure") {
          throw new Error(errorMessage(payload, "ChemEAGLE could not process this source."));
        }

        timeout = setTimeout(poll, 3000);
      } catch (error) {
        if (cancelled) return;
        const message =
          error instanceof Error ? error.message : "Status check failed.";
        setFailure(message);
        setRunState("error");
        setTaskId(null);
        toast.error(message);
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timeout) clearTimeout(timeout);
    };
  }, [taskId]);

  function selectFile(nextFile: File | null) {
    if (!nextFile) return;
    const isPdf = nextFile.type === "application/pdf";
    if (inputMode === "image" && isPdf) {
      toast.error("Choose a PNG, JPG, WebP, or TIFF image.");
      return;
    }
    if (inputMode === "pdf" && !isPdf) {
      toast.error("Choose a PDF document.");
      return;
    }
    if (nextFile.size > 50 * 1024 * 1024) {
      toast.error("The maximum upload size is 50 MB.");
      return;
    }
    setFile(nextFile);
    setFailure(null);
    setResult(null);
    setRunState("idle");
  }

  function changeMode(value: string | number) {
    const nextMode = String(value) as InputMode;
    setInputMode(nextMode);
    setFile(null);
    setResult(null);
    setFailure(null);
    setRunState("idle");
    setTaskId(null);
  }

  async function startExtraction() {
    if (!canSubmit || isRunning) return;
    setFailure(null);
    setResult(null);
    setRunState("submitting");

    const body = new FormData();
    body.append("kind", inputMode);
    if (inputMode === "url") {
      body.append("url", sourceUrl.trim());
      body.append("urlKind", urlKind);
    } else if (file) {
      body.append("file", file, file.name);
    }

    try {
      const response = await fetch("/api/chemeagle/process", {
        method: "POST",
        body,
      });
      const payload = (await response.json()) as unknown;
      if (!response.ok) {
        throw new Error(errorMessage(payload, "Unable to start extraction."));
      }

      const nextTaskId = getTaskId(payload);
      if (nextTaskId) {
        setTaskId(nextTaskId);
        setRunState("queued");
        toast.success("Extraction queued");
      } else {
        setResult(payload);
        setRunState("completed");
        toast.success("Extraction complete");
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to start extraction.";
      setFailure(message);
      setRunState("error");
      toast.error(message);
    }
  }

  function reset() {
    setFile(null);
    setSourceUrl("");
    setTaskId(null);
    setResult(null);
    setFailure(null);
    setRunState("idle");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function copyResult() {
    if (!result) return;
    await navigator.clipboard.writeText(prettyJson(result));
    toast.success("JSON copied to clipboard");
  }

  function downloadResult() {
    if (!result) return;
    const blob = new Blob([prettyJson(result)], { type: "application/json" });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = `chemeagle-${taskId || Date.now()}.json`;
    anchor.click();
    URL.revokeObjectURL(href);
  }

  return (
    <main className="min-h-screen bg-background">
      <header className="sticky top-0 z-10 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-screen-2xl items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <Image
              alt="ChemEAGLE"
              className="size-9 rounded-lg"
              height={36}
              priority
              src="/chemeagle-logo.png"
              width={36}
            />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="truncate text-base font-semibold">ChemEAGLE</h1>
                <Badge variant="secondary">Workspace</Badge>
              </div>
              <p className="hidden text-xs text-muted-foreground sm:block">
                Multimodal chemical literature extraction
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge className="hidden sm:inline-flex" variant="outline">
              <CheckCircle2 data-icon="inline-start" />
              API proxy
            </Badge>
            <a
              className={buttonVariants({ variant: "ghost", size: "icon" })}
              href="https://github.com/Tew12345678910/ChemEagle"
              rel="noreferrer"
              target="_blank"
            >
              <GitFork />
              <span className="sr-only">Open GitHub repository</span>
            </a>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-screen-2xl gap-6 p-4 sm:p-6 xl:grid-cols-[420px_minmax(0,1fr)]">
        <aside className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles />
                New extraction
              </CardTitle>
              <CardDescription>
                Upload a reaction figure, a paper, or provide a public URL.
              </CardDescription>
              {file || sourceUrl || result ? (
                <CardAction>
                  <Tooltip>
                    <TooltipTrigger
                      render={
                        <Button onClick={reset} size="icon-sm" variant="ghost" />
                      }
                    >
                      <RotateCcw />
                      <span className="sr-only">Reset workspace</span>
                    </TooltipTrigger>
                    <TooltipContent>Reset workspace</TooltipContent>
                  </Tooltip>
                </CardAction>
              ) : null}
            </CardHeader>
            <CardContent>
              <Tabs onValueChange={changeMode} value={inputMode}>
                <TabsList className="grid w-full grid-cols-3">
                  <TabsTrigger value="image">
                    <FileImage data-icon="inline-start" />
                    Image
                  </TabsTrigger>
                  <TabsTrigger value="pdf">
                    <FileText data-icon="inline-start" />
                    PDF
                  </TabsTrigger>
                  <TabsTrigger value="url">
                    <Link2 data-icon="inline-start" />
                    URL
                  </TabsTrigger>
                </TabsList>

                <TabsContent className="pt-4" value="image">
                  <UploadField
                    accept={FILE_ACCEPT.image}
                    file={file}
                    inputRef={fileInputRef}
                    label="Reaction image"
                    onSelect={selectFile}
                  />
                </TabsContent>
                <TabsContent className="pt-4" value="pdf">
                  <UploadField
                    accept={FILE_ACCEPT.pdf}
                    file={file}
                    inputRef={fileInputRef}
                    label="Scientific paper"
                    onSelect={selectFile}
                  />
                </TabsContent>
                <TabsContent className="pt-4" value="url">
                  <FieldGroup>
                    <Field>
                      <FieldLabel htmlFor="source-url">Public source URL</FieldLabel>
                      <Input
                        id="source-url"
                        onChange={(event) => setSourceUrl(event.target.value)}
                        placeholder="https://example.org/paper.pdf"
                        type="url"
                        value={sourceUrl}
                      />
                      <FieldDescription>
                        The ChemEAGLE server downloads and processes the source.
                      </FieldDescription>
                    </Field>
                    <Field>
                      <FieldLabel>Source type</FieldLabel>
                      <Tabs
                        onValueChange={(value) =>
                          setUrlKind(String(value) as "image" | "pdf")
                        }
                        value={urlKind}
                      >
                        <TabsList className="grid w-full grid-cols-2">
                          <TabsTrigger value="image">Image</TabsTrigger>
                          <TabsTrigger value="pdf">PDF</TabsTrigger>
                        </TabsList>
                      </Tabs>
                    </Field>
                  </FieldGroup>
                </TabsContent>
              </Tabs>
            </CardContent>
            <CardFooter className="flex-col items-stretch gap-3">
              {isRunning ? (
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      {runState === "submitting"
                        ? "Uploading source"
                        : "Agents are extracting reactions"}
                    </span>
                    <span>{runState === "submitting" ? "Starting" : "In progress"}</span>
                  </div>
                  <Progress value={runState === "submitting" ? 24 : 68} />
                </div>
              ) : null}
              <Button
                disabled={!canSubmit || isRunning}
                onClick={startExtraction}
                size="lg"
              >
                {isRunning ? (
                  <Spinner data-icon="inline-start" />
                ) : (
                  <Beaker data-icon="inline-start" />
                )}
                {isRunning ? "Processing" : "Extract chemical data"}
                {!isRunning ? <ArrowRight data-icon="inline-end" /> : null}
              </Button>
            </CardFooter>
          </Card>

          <Alert>
            <Sparkles />
            <AlertTitle>What ChemEAGLE extracts</AlertTitle>
            <AlertDescription>
              Reactants, products, SMILES, reaction conditions, R-group variants,
              and structured records ready for downstream analysis.
            </AlertDescription>
          </Alert>

          <Card size="sm">
            <CardHeader>
              <CardTitle>Engine</CardTitle>
              <CardDescription>
                Requests are proxied through this app, so your API key is never sent
                to the browser.
              </CardDescription>
              <CardAction>
                <Badge variant="outline">ChemEAGLE v1</Badge>
              </CardAction>
            </CardHeader>
            <CardFooter>
              <a
                className={buttonVariants({ variant: "ghost", size: "sm" })}
                href="https://app.chemeagle.net/api/v1/docs"
                rel="noreferrer"
                target="_blank"
              >
                API documentation
                <ExternalLink data-icon="inline-end" />
              </a>
            </CardFooter>
          </Card>
        </aside>

        <section className="min-w-0">
          {failure ? (
            <Alert className="mb-4" variant="destructive">
              <X />
              <AlertTitle>Extraction failed</AlertTitle>
              <AlertDescription>{failure}</AlertDescription>
            </Alert>
          ) : null}

          <Card className="min-h-[calc(100vh-7.5rem)]">
            <CardHeader>
              <CardTitle>Extraction workspace</CardTitle>
              <CardDescription>
                Review the source and inspect structured chemical data side by side.
              </CardDescription>
              {result ? (
                <CardAction className="flex items-center gap-1">
                  <Tooltip>
                    <TooltipTrigger
                      render={
                        <Button onClick={copyResult} size="icon-sm" variant="ghost" />
                      }
                    >
                      <Clipboard />
                      <span className="sr-only">Copy result JSON</span>
                    </TooltipTrigger>
                    <TooltipContent>Copy JSON</TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger
                      render={
                        <Button
                          onClick={downloadResult}
                          size="icon-sm"
                          variant="ghost"
                        />
                      }
                    >
                      <Download />
                      <span className="sr-only">Download result JSON</span>
                    </TooltipTrigger>
                    <TooltipContent>Download JSON</TooltipContent>
                  </Tooltip>
                </CardAction>
              ) : null}
            </CardHeader>
            <CardContent className="flex flex-1 flex-col">
              {!file && inputMode !== "url" && !result ? (
                <Empty className="min-h-[34rem] border">
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <Beaker />
                    </EmptyMedia>
                    <EmptyTitle>Ready for a chemical source</EmptyTitle>
                    <EmptyDescription>
                      Choose an image or PDF to preview it here, then start the
                      multi-agent extraction workflow.
                    </EmptyDescription>
                  </EmptyHeader>
                </Empty>
              ) : null}

              {(file && previewUrl) || (inputMode === "url" && sourceUrl) ? (
                <div
                  className={cn(
                    "grid min-h-[34rem] gap-4",
                    Boolean(result) &&
                      "lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]",
                  )}
                >
                  <div className="flex min-w-0 flex-col gap-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {file?.name || sourceUrl}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {file
                            ? `${(file.size / 1024 / 1024).toFixed(2)} MB`
                            : `Remote ${urlKind.toUpperCase()}`}
                        </p>
                      </div>
                      <Badge variant="outline">Source</Badge>
                    </div>
                    {file && previewUrl ? (
                      <SourcePreview file={file} previewUrl={previewUrl} />
                    ) : (
                      <Empty className="min-h-96 border">
                        <EmptyHeader>
                          <EmptyMedia variant="icon">
                            <Link2 />
                          </EmptyMedia>
                          <EmptyTitle>Remote source</EmptyTitle>
                          <EmptyDescription>{sourceUrl}</EmptyDescription>
                        </EmptyHeader>
                      </Empty>
                    )}
                  </div>

                  {result ? (
                    <ResultsPanel
                      reactions={reactions}
                      result={result}
                      resultCount={resultCount}
                    />
                  ) : isRunning ? (
                    <ProcessingPanel />
                  ) : null}
                </div>
              ) : null}

              {result && !file && inputMode !== "url" ? (
                <ResultsPanel
                  reactions={reactions}
                  result={result}
                  resultCount={resultCount}
                />
              ) : null}
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}

function UploadField({
  accept,
  file,
  inputRef,
  label,
  onSelect,
}: {
  accept: string;
  file: File | null;
  inputRef: React.RefObject<HTMLInputElement | null>;
  label: string;
  onSelect: (file: File | null) => void;
}) {
  return (
    <Field>
      <FieldLabel htmlFor="source-file">{label}</FieldLabel>
      <label
        className="flex min-h-44 cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border border-dashed bg-muted/30 p-6 text-center transition-colors hover:bg-muted/60"
        htmlFor="source-file"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          onSelect(event.dataTransfer.files.item(0));
        }}
      >
        <span className="flex size-10 items-center justify-center rounded-full bg-background shadow-sm ring-1 ring-border">
          <UploadCloud />
        </span>
        <span className="flex flex-col gap-1">
          <span className="font-medium">
            {file ? file.name : "Drop a file here or click to browse"}
          </span>
          <span className="text-xs text-muted-foreground">
            {file
              ? `${(file.size / 1024 / 1024).toFixed(2)} MB selected`
              : "Maximum file size: 50 MB"}
          </span>
        </span>
      </label>
      <Input
        accept={accept}
        className="sr-only"
        id="source-file"
        onChange={(event) => onSelect(event.target.files?.item(0) || null)}
        ref={inputRef}
        type="file"
      />
      <FieldDescription>
        Files are sent through the local server route directly to ChemEAGLE.
      </FieldDescription>
    </Field>
  );
}

function ProcessingPanel() {
  return (
    <div className="flex min-h-96 flex-col gap-4 rounded-lg border p-5">
      <div className="flex items-center gap-3">
        <Spinner />
        <div>
          <p className="font-medium">Agents are working</p>
          <p className="text-sm text-muted-foreground">
            Complex figures and PDFs can take several minutes.
          </p>
        </div>
      </div>
      <Separator />
      <div className="flex flex-col gap-3">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  );
}

function ResultsPanel({
  reactions,
  result,
  resultCount,
}: {
  reactions: Reaction[];
  result: unknown;
  resultCount: number;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Recognition results</p>
          <p className="text-xs text-muted-foreground">
            {reactions.length} reactions across {resultCount} result
            {resultCount === 1 ? "" : "s"}
          </p>
        </div>
        <Badge>
          <CheckCircle2 data-icon="inline-start" />
          Complete
        </Badge>
      </div>
      <Tabs className="min-h-0 flex-1" defaultValue="structured">
        <TabsList>
          <TabsTrigger value="structured">Structured</TabsTrigger>
          <TabsTrigger value="json">Raw JSON</TabsTrigger>
        </TabsList>
        <TabsContent className="min-h-0 pt-2" value="structured">
          <ScrollArea className="h-[32rem] pr-3">
            {reactions.length > 0 ? (
              <div className="flex flex-col gap-3">
                {reactions.map((reaction) => (
                  <ReactionCard key={reaction.id} reaction={reaction} />
                ))}
              </div>
            ) : (
              <Empty className="h-80 border">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <FileText />
                  </EmptyMedia>
                  <EmptyTitle>No normalized reaction list found</EmptyTitle>
                  <EmptyDescription>
                    The request completed, but its response uses a different shape.
                    Inspect Raw JSON for the full output.
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            )}
          </ScrollArea>
        </TabsContent>
        <TabsContent className="min-h-0 pt-2" value="json">
          <ScrollArea className="h-[32rem] rounded-lg border bg-muted/40 p-4">
            <pre className="text-xs leading-relaxed">{prettyJson(result)}</pre>
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </div>
  );
}
