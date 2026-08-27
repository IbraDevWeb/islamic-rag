import { NextResponse } from "next/server";

const RAG_API_URL = process.env.RAG_API_URL ?? "http://api:8000";

function upstreamError(payload: unknown, fallback: string): string {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof (payload as { detail?: unknown }).detail === "string"
  ) {
    return (payload as { detail: string }).detail;
  }
  return fallback;
}

async function jsonOrNull(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function GET() {
  try {
    const response = await fetch(`${RAG_API_URL}/health/dependencies`, {
      cache: "no-store",
    });
    const payload = await jsonOrNull(response);
    if (!response.ok) {
      return NextResponse.json(
        { status: "degraded", detail: upstreamError(payload, "Backend indisponible") },
        { status: 502 },
      );
    }
    return NextResponse.json(payload, { status: 200 });
  } catch {
    return NextResponse.json(
      { status: "offline", detail: "Impossible de joindre l'API Islamic RAG." },
      { status: 503 },
    );
  }
}

export async function POST(request: Request) {
  let body: {
    question?: string;
    mode?: "synthesis" | "evidence";
    limit?: number;
    work_uri?: string;
    verify_claims?: boolean;
  };

  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Requête JSON invalide." }, { status: 400 });
  }

  const question = body.question?.trim() ?? "";
  if (!question) {
    return NextResponse.json({ detail: "La question est vide." }, { status: 400 });
  }

  const mode = body.mode === "evidence" ? "evidence" : "synthesis";
  const limit = Math.min(Math.max(Number(body.limit ?? 5), 1), 10);
  const workUri = body.work_uri?.trim() || undefined;

  const query = new URLSearchParams({
    q: question,
    limit: String(limit),
  });
  if (workUri) query.set("work_uri", workUri);

  try {
    const evidenceResponse = await fetch(
      `${RAG_API_URL}/evidence-bundle?${query.toString()}`,
      { cache: "no-store" },
    );
    const evidence = await jsonOrNull(evidenceResponse);

    if (!evidenceResponse.ok) {
      return NextResponse.json(
        {
          detail: upstreamError(
            evidence,
            "Impossible de construire le dossier de preuves.",
          ),
        },
        { status: evidenceResponse.status >= 500 ? 502 : evidenceResponse.status },
      );
    }

    if (mode === "evidence") {
      return NextResponse.json({ mode, evidence });
    }

    const synthesisResponse = await fetch(`${RAG_API_URL}/generate-synthesis`, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify({
        question,
        limit,
        work_uri: workUri ?? null,
        include_rejected: false,
        verify_claims: body.verify_claims ?? true,
      }),
      cache: "no-store",
    });
    const synthesis = await jsonOrNull(synthesisResponse);

    if (!synthesisResponse.ok) {
      return NextResponse.json(
        {
          detail: upstreamError(synthesis, "La synthèse n'a pas pu être générée."),
          evidence,
        },
        { status: synthesisResponse.status >= 500 ? 502 : synthesisResponse.status },
      );
    }

    return NextResponse.json({ mode, evidence, synthesis });
  } catch {
    return NextResponse.json(
      { detail: "Le frontend n'arrive pas à joindre l'API Islamic RAG." },
      { status: 503 },
    );
  }
}
