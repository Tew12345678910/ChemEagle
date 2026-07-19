import { NextResponse } from "next/server";

const DEFAULT_BASE_URL = "https://app.chemeagle.net";
const MAX_FILE_SIZE = 50 * 1024 * 1024;

export const runtime = "nodejs";
export const maxDuration = 300;

function apiBaseUrl() {
  return (process.env.CHEMEAGLE_API_BASE_URL || DEFAULT_BASE_URL).replace(
    /\/$/,
    "",
  );
}

function headers(contentType?: string): HeadersInit {
  const result: Record<string, string> = { Accept: "application/json" };
  if (process.env.CHEMEAGLE_API_KEY) {
    result["X-API-Key"] = process.env.CHEMEAGLE_API_KEY;
  }
  if (contentType) result["Content-Type"] = contentType;
  return result;
}

async function upstreamJson(response: Response) {
  const text = await response.text();
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return {
      success: false,
      error_code: "invalid_upstream_response",
      message: text.slice(0, 300) || "ChemEAGLE returned an empty response.",
    };
  }
}

export async function POST(request: Request) {
  try {
    let form: FormData;
    try {
      form = await request.formData();
    } catch {
      return NextResponse.json(
        {
          success: false,
          message: "Send the source as multipart form data.",
        },
        { status: 400 },
      );
    }
    const kind = form.get("kind");

    if (kind === "url") {
      const url = form.get("url");
      const urlKind = form.get("urlKind");
      if (typeof url !== "string" || !url.trim()) {
        return NextResponse.json(
          { success: false, message: "Enter a public image or PDF URL." },
          { status: 400 },
        );
      }

      const response = await fetch(`${apiBaseUrl()}/api/v1/process_url`, {
        method: "POST",
        headers: headers("application/json"),
        body: JSON.stringify({
          url: url.trim(),
          type: urlKind === "image" ? "image" : "pdf",
          sync: false,
        }),
        cache: "no-store",
      });
      return NextResponse.json(await upstreamJson(response), {
        status: response.status,
      });
    }

    const file = form.get("file");
    if (!(file instanceof File)) {
      return NextResponse.json(
        { success: false, message: "Choose an image or PDF to process." },
        { status: 400 },
      );
    }
    if (file.size > MAX_FILE_SIZE) {
      return NextResponse.json(
        { success: false, message: "The maximum upload size is 50 MB." },
        { status: 413 },
      );
    }

    const isPdf = file.type === "application/pdf" || kind === "pdf";
    const upstreamForm = new FormData();
    upstreamForm.append("file", file, file.name);
    upstreamForm.append("sync", "false");

    const endpoint = isPdf ? "process_pdf" : "process_image";
    const response = await fetch(`${apiBaseUrl()}/api/v1/${endpoint}`, {
      method: "POST",
      headers: headers(),
      body: upstreamForm,
      cache: "no-store",
    });

    return NextResponse.json(await upstreamJson(response), {
      status: response.status,
    });
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
