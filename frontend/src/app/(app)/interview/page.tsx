import type { Metadata } from "next";
import { InterviewClient } from "./interview-client";

export const metadata: Metadata = { title: "My handover" };

export default function Page() {
  return <InterviewClient />;
}
