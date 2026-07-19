import { NextResponse } from "next/server";

const DEFAULT_BASE_URL = "https://app.chemeagle.net";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  context: { params: Promise<{ taskId: string }> },
) {
  const { taskId } = await context.params;
  const baseUrl = (
    process.env.CHEMEAGLE_API_BASE_URL || DEFAULT_BASE_URL
  ).replace(/\/$/, "");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (process.env.CHEMEAGLE_API_KEY) {
    headers["X-API-Key"] = process.env.CHEMEAGLE_API_KEY;
  }

  try {
    const response = await fetch(
      `${baseUrl}/api/v1/status/${encodeURIComponent(taskId)}`,
      { headers, cache: "no-store" },
    );
    const text = await response.text();
    let payload: unknown;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = {
        success: false,
        error_code: "invalid_upstream_response",
        message: text.slice(0, 300) || "ChemEAGLE returned an empty response.",
      };
    }
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        success: false,
        error_code: "proxy_error",
        message:
          error instanceof Error ? error.message : "Unable to reach ChemEAGLE.",
      },
      { status: 502 },
    );
  }
}
