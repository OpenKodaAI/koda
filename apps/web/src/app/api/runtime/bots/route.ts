import { NextResponse } from "next/server";
import { getOperationalBotStatsList } from "@/lib/runtime-dashboard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  try {
    const payload = await getOperationalBotStatsList();
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Unable to load runtime bot stats",
      },
      { status: 500 },
    );
  }
}
