import { NextResponse } from "next/server";

interface PilotLeadPayload {
  name?: string;
  email?: string;
  organization?: string;
  siteType?: string;
  message?: string;
  website?: string;
}

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function clean(value: unknown, maxLength: number): string {
  if (typeof value !== "string") return "";
  return value.trim().slice(0, maxLength);
}

async function sendNotificationEmail(payload: {
  name: string;
  email: string;
  organization: string;
  siteType: string;
  message: string;
}) {
  const resendApiKey = process.env.RESEND_API_KEY;
  const toEmail = process.env.LEADS_TO_EMAIL;
  const fromEmail = process.env.LEADS_FROM_EMAIL;

  if (!resendApiKey || !toEmail || !fromEmail) {
    return;
  }

  const subject = `New GWhFi pilot lead: ${payload.organization}`;
  const text = [
    "New pilot call request",
    "",
    `Name: ${payload.name}`,
    `Email: ${payload.email}`,
    `Organisation: ${payload.organization}`,
    `Site type: ${payload.siteType}`,
    "",
    "Message:",
    payload.message || "(none)",
  ].join("\n");

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${resendApiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: fromEmail,
      to: [toEmail],
      subject,
      text,
      reply_to: payload.email,
    }),
  });

  if (!response.ok) {
    throw new Error("Failed to send lead notification");
  }
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as PilotLeadPayload;

    const website = clean(body.website, 200);
    if (website) {
      return NextResponse.json({ ok: true });
    }

    const name = clean(body.name, 120);
    const email = clean(body.email, 160);
    const organization = clean(body.organization, 180);
    const siteType = clean(body.siteType, 60);
    const message = clean(body.message, 2000);

    if (!name || !email || !organization || !siteType) {
      return NextResponse.json(
        { error: "Missing required fields" },
        { status: 400 }
      );
    }

    if (!isValidEmail(email)) {
      return NextResponse.json(
        { error: "Please enter a valid email" },
        { status: 400 }
      );
    }

    await sendNotificationEmail({
      name,
      email,
      organization,
      siteType,
      message,
    });

    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json(
      { error: "Could not submit pilot request" },
      { status: 500 }
    );
  }
}
